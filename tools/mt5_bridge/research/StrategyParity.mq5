#property strict
#property version "1.10"
#property description "Research only. Refuses initialization outside Strategy Tester."
#property tester_file "s11b_parity.csv"
#property tester_file "s11b_numeric.csv"
#include "ParityDecimal.mqh"

input bool MathOnly=true;
input bool SimulateOrders=false;
input datetime ObservationStart=D'2026.11.04 15:00';
input datetime ObservationEnd=D'2026.11.04 16:00';
input double Threshold=10;
input double RiskFraction=0.01;
input double ResearchRiskCap=20;
input double ResearchVolumeCap=0.01;
input double ATRMultiplier=1.5;
input double RewardRisk=2;

datetime last_completed=0;
int accepted=0, ledger=INVALID_HANDLE;

// CPython 3.12 float sum uses Neumaier compensation before the simple average.
void SumTerm(double x,double &total,double &correction)
{
   double next=total+x;
   correction+=MathAbs(total)>=MathAbs(x)?(total-next)+x:(x-next)+total;
   total=next;
}

// Same simple-window definitions as Python IndicatorEngine, NOT Wilder iRSI/iATR.
bool Indicators(const MqlRates &bars[],const int n,double &rsi,double &atr)
{
   if(n<=14) return false;
   double gain=0,loss=0,tr=0,cg=0,cl=0,ct=0;
   for(int i=n-14;i<n;i++)
   {
      double change=bars[i].close-bars[i-1].close;
      SumTerm(MathMax(change,0),gain,cg); SumTerm(MathMax(-change,0),loss,cl);
      SumTerm(MathMax(bars[i].high-bars[i].low,
          MathMax(MathAbs(bars[i].high-bars[i-1].close),MathAbs(bars[i].low-bars[i-1].close))),tr,ct);
   }
   double avg_gain=(gain+cg)/14,avg_loss=(loss+cl)/14;
   rsi=avg_loss==0 ? 100 : 100-100/(1+avg_gain/avg_loss);
   atr=(tr+ct)/14;
   return true;
}

bool Proposal(string entry,double atr,string equity,string tick,string value,
              string minimum,string maximum,string step,string fraction,
              string riskcap,string volumecap,string multiple,string rr,
              double &sl,double &tp,double &volume,double &risk,string side="BUY")
{
   volume=-1; risk=-1;
   string inputs[12];
   inputs[0]=entry; inputs[1]=equity; inputs[2]=tick; inputs[3]=value;
   inputs[4]=minimum; inputs[5]=maximum; inputs[6]=step; inputs[7]=fraction;
   inputs[8]=riskcap; inputs[9]=volumecap; inputs[10]=multiple; inputs[11]=rr;
   for(int i=0;i<ArraySize(inputs);i++)
      if(DRead(inputs[i])=="" || DCmp(inputs[i],"0")<=0) return false;
   if(!MathIsValidNumber(atr) || atr<=0 || DCmp(maximum,minimum)<0 ||
      (side!="BUY" && side!="SELL")) return false;
   string sign=side=="BUY"?"1":"-1";
   string stop=DTick(DSub(entry,DMul(DMul(sign,DFloat(atr)),multiple)),tick);
   if(stop=="") return false;
   sl=StringToDouble(stop);
   string distance=DMul(sign,DSub(entry,stop));
   if(distance=="" || DCmp(stop,"0")<=0 || DCmp(distance,"0")<=0 ||
      DCmp(distance,DMul(entry,"0.20"))>0) return false;
   string target=DTick(DAdd(entry,DMul(DMul(sign,distance),rr)),tick);
   if(target=="") return false;
   tp=StringToDouble(target);
   string per_lot=DMul(DDiv(distance,tick),value);
   string budget=DMin(DMul(equity,fraction),riskcap);
   string cap=DMin(volumecap,maximum);
   string sized=DMul(DIntegral(DDiv(DMin(DDiv(budget,per_lot),cap),step),false),step);
   if(sized=="" || DCmp(sized,minimum)<0 || DCmp(target,"0")<=0) return false;
   string actual=DMul(per_lot,sized);
   if(actual=="") return false;
   volume=StringToDouble(sized); risk=StringToDouble(actual);
   return DCmp(actual,riskcap)<=0 && DCmp(sized,cap)<=0;
}

int RunFixtures()
{
   int source=FileOpen("s11b_parity.csv",FILE_READ|FILE_CSV|FILE_ANSI,',');
   int output=FileOpen("s11b_parity_result.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(source==INVALID_HANDLE || output==INVALID_HANDLE)
   {
      if(source!=INVALID_HANDLE) FileClose(source);
      if(output!=INVALID_HANDLE) FileClose(output);
      return -1;
   }
   int count=0;
   while(!FileIsEnding(source))
   {
      string name=FileReadString(source);
      if(name=="") break;
      int n=(int)FileReadNumber(source);
      if(n<1 || n>100) { FileClose(source); FileClose(output); return -1; }
      MqlRates bars[]; ArrayResize(bars,n);
      for(int i=0;i<n;i++)
      {
         bars[i].time=(datetime)FileReadNumber(source);
         bars[i].close=FileReadNumber(source);
         bars[i].high=FileReadNumber(source); bars[i].low=FileReadNumber(source);
      }
      string entry=FileReadString(source), equity=FileReadString(source);
      string tick=FileReadString(source),value=FileReadString(source);
      string minimum=FileReadString(source),maximum=FileReadString(source),step=FileReadString(source);
      string fraction=FileReadString(source),riskcap=FileReadString(source),volumecap=FileReadString(source);
      string multiple=FileReadString(source),rr=FileReadString(source);
      double threshold=FileReadNumber(source);
      double previous=FileReadNumber(source);
      FileReadNumber(source); // Consume legacy expected-RSI column; never use it for native decisions.
      bool active=(bool)FileReadNumber(source);
      string side="BUY";
      if(!FileIsLineEnding(source) && !FileIsEnding(source)) side=FileReadString(source);
      double rsi=-1,atr=-1,sl=-1,tp=-1,volume=-1,risk=-1;
      bool warm=Indicators(bars,n,rsi,atr);
      bool valid=warm && Proposal(entry,atr,equity,tick,value,minimum,maximum,step,
                                 fraction,riskcap,volumecap,multiple,rr,sl,tp,volume,risk,side);
      FileWrite(output,name,(long)bars[n-1].time,DoubleToString(rsi,12),DoubleToString(atr,12),
                DoubleToString(sl,12),DoubleToString(tp,12),DoubleToString(volume,12),DoubleToString(risk,12),
                (int)(rsi>threshold),(int)(previous<=threshold && rsi>threshold),
                (int)(valid && rsi>threshold && !active));
      count++;
   }
   FileClose(source); FileClose(output);
   return count;
}

int RunScalarFixtures()
{
   int source=FileOpen("s11b_numeric.csv",FILE_READ|FILE_CSV|FILE_ANSI,',');
   int output=FileOpen("s11b_numeric_result.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(source==INVALID_HANDLE || output==INVALID_HANDLE)
   {
      if(source!=INVALID_HANDLE) FileClose(source);
      if(output!=INVALID_HANDLE) FileClose(output);
      return -1;
   }
   int count=0;
   while(!FileIsEnding(source))
   {
      string name=FileReadString(source); if(name=="") break;
      string operation=FileReadString(source),a=FileReadString(source),b=FileReadString(source),answer="";
      a=DRead(a); b=DRead(b);
      if(operation=="TICK") answer=DTick(a,b);
      else if(operation=="FLOOR" && a!="" && b!="" && DCmp(b,"0")>0 && DCmp(a,"0")>=0)
         answer=DMul(DIntegral(DDiv(a,b),false),b);
      else if(operation=="MUL") answer=DMul(a,b);
      else if(operation=="DIV") answer=DDiv(a,b);
      else if(operation=="ADD") answer=DAdd(a,b);
      else if(operation=="DOUBLE" && a!="") answer=DFloat(StringToDouble(a));
      FileWrite(output,name,answer==""?"INVALID":answer);
      count++;
   }
   FileClose(source); FileClose(output); return count;
}

int OnInit()
{
   if(!MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION)) return INIT_FAILED;
   if(MathOnly && SimulateOrders) return INIT_PARAMETERS_INCORRECT;
   if(RunFixtures()<=0) return INIT_FAILED;
   if(RunScalarFixtures()<=0) return INIT_FAILED;
   if(MathOnly) { Print("PARITY_MATH_ONLY fixtures complete; no market/order path"); return INIT_SUCCEEDED; }
   if(ObservationStart>=ObservationEnd || RiskFraction<=0 || RiskFraction>0.02 ||
      ATRMultiplier<=0 || RewardRisk<0.5 || RewardRisk>10 || ResearchRiskCap<=0 || ResearchVolumeCap<=0)
      return INIT_PARAMETERS_INCORRECT;
   ledger=FileOpen("s11b_completed_bars.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(ledger==INVALID_HANDLE) return INIT_FAILED;
   Print("S11B TESTER_RESEARCH research-parity/v1 tester-only initialized");
   return INIT_SUCCEEDED;
}

void OnTick()
{
   if(!MQLInfoInteger(MQL_TESTER) || MathOnly) return;
   MqlRates bars[];
   if(CopyRates(_Symbol,PERIOD_M1,1,15,bars)!=15) return;
   datetime completed=bars[14].time;
   if(completed==last_completed || completed<ObservationStart || completed>=ObservationEnd) return;
   last_completed=completed;
   double rsi,atr;
   if(!Indicators(bars,15,rsi,atr)) return;
   MqlTick quote;
   if(!SymbolInfoTick(_Symbol,quote)) return;
   double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   double value=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   double sl=-1,tp=-1,volume=-1,risk=-1;
   bool valid=Proposal(DFloat(quote.ask),atr,DFloat(AccountInfoDouble(ACCOUNT_EQUITY)),DFloat(tick),DFloat(value),
             DFloat(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN)),DFloat(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX)),
             DFloat(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP)),DFloat(RiskFraction),DFloat(ResearchRiskCap),
             DFloat(ResearchVolumeCap),DFloat(ATRMultiplier),DFloat(RewardRisk),sl,tp,volume,risk);
   FileWrite(ledger,(long)completed,DoubleToString(rsi,12),DoubleToString(atr,12),
             (int)(rsi>Threshold),DoubleToString(quote.ask,12),DoubleToString(sl,12),
             DoubleToString(tp,12),DoubleToString(volume,12),DoubleToString(risk,12),
             (int)valid,PositionsTotal(),accepted);
   // One bounded virtual opening only; never attach this EA to a normal chart.
   if(!SimulateOrders || !valid || rsi<=Threshold || PositionsTotal()>0 || OrdersTotal()>0 || accepted>0) return;
   double minimum=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   if(quote.bid-sl<minimum || tp-quote.bid<minimum) return;
   MqlTradeRequest request={}; MqlTradeResult result={}; MqlTradeCheckResult check={};
   request.action=TRADE_ACTION_DEAL; request.symbol=_Symbol; request.type=ORDER_TYPE_BUY;
   request.price=quote.ask; request.volume=volume; request.sl=sl; request.tp=tp;
   request.deviation=10; request.comment="HISTORICAL_SIMULATION";
   long filling=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
   request.type_filling=(filling&SYMBOL_FILLING_FOK)!=0 ? ORDER_FILLING_FOK : ORDER_FILLING_IOC;
   if(!MQLInfoInteger(MQL_TESTER)) return;
   if(!OrderCheck(request,check)) { Print("S11B virtual check blocked: ",check.retcode); return; }
   // Count the attempt before sending: no automatic retry even for uncertain results.
   accepted++;
   if(!MQLInfoInteger(MQL_TESTER)) return;
   bool sent=OrderSend(request,result);
   Print("S11B virtual submission sent=",sent," retcode=",result.retcode);
}

double OnTester() { return 1; }
void OnDeinit(const int reason) { if(ledger!=INVALID_HANDLE) FileClose(ledger); }
