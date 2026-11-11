#property strict
#property version "1.00"
#property tester_file "replay_schedule.csv"

input bool ApprovedResearchReplay=false;

struct Signal { long time; int index; string action; int triggered; };
Signal schedule[];
int cursor=0, out=INVALID_HANDLE, digits=0, money_digits=0;
long start_ms=0,end_ms=0,offset_ms=0,max_delay=0,last_tick=-1;
string side;
double volume,stop,target,risk_cap,risk_fraction,point;
bool failed=false,started=false,finished=false;

bool TesterOnly()
{
   return MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_OPTIMIZATION) && !MQLInfoInteger(MQL_FORWARD);
}

int OnInit()
{
   if(!TesterOnly() || !ApprovedResearchReplay) return INIT_FAILED;
   int f=FileOpen("replay_schedule.csv",FILE_READ|FILE_CSV|FILE_ANSI,',');
   if(f==INVALID_HANDLE) return INIT_FAILED;
   string schema=FileReadString(f), job=FileReadString(f), part=FileReadString(f);
   string symbol=FileReadString(f);
   int seconds=(int)FileReadNumber(f);
   start_ms=1000*(long)FileReadNumber(f); end_ms=1000*(long)FileReadNumber(f);
   offset_ms=1000*(long)FileReadNumber(f); side=FileReadString(f);
   volume=FileReadNumber(f); stop=FileReadNumber(f); target=FileReadNumber(f);
   risk_cap=FileReadNumber(f); max_delay=(long)FileReadNumber(f);
   string currency=FileReadString(f);
   double deviation=FileReadNumber(f);
   risk_fraction=FileReadNumber(f);
   int count=(int)FileReadNumber(f);
   point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   money_digits=(int)AccountInfoInteger(ACCOUNT_CURRENCY_DIGITS);
   if(schema!="SIGNAL_REPLAY_V1" || StringLen(job)!=64 || (part!="IS" && part!="OOS")
      || symbol!=_Symbol || seconds!=PeriodSeconds(_Period) || start_ms<=0 || end_ms<=start_ms
      || MathAbs(offset_ms)>86400000 || (side!="BUY" && side!="SELL")
      || volume<=0 || stop<=0 || target<=0 || risk_cap<=0 || point<=0 || max_delay<=0
      || currency!=AccountInfoString(ACCOUNT_CURRENCY) || deviation!=0 || risk_fraction<=0 || risk_fraction>1
      || count<1 || count>100000 || ArrayResize(schedule,count)!=count
      || !(SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE)&SYMBOL_FILLING_FOK))
   { FileClose(f); return INIT_PARAMETERS_INCORRECT; }
   for(int i=0;i<count;i++)
   {
      schedule[i].time=1000*(long)FileReadNumber(f);
      schedule[i].index=(int)FileReadNumber(f);
      schedule[i].action=FileReadString(f);
      schedule[i].triggered=(int)FileReadNumber(f);
      if(schedule[i].index!=i || schedule[i].time<=start_ms || schedule[i].time>end_ms
         || (i>0 && schedule[i].time<schedule[i-1].time)
         || (schedule[i].action!="ENTRY" && schedule[i].action!="EXIT")
         || schedule[i].triggered<0 || schedule[i].triggered>1)
      { FileClose(f); return INIT_PARAMETERS_INCORRECT; }
   }
   if(FileReadString(f)!="END" || !FileIsEnding(f)) { FileClose(f); return INIT_PARAMETERS_INCORRECT; }
   FileClose(f);
   out=FileOpen("replay_result.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(out==INVALID_HANDLE) return INIT_FAILED;
   FileWrite(out,"META",job,part,(int)TerminalInfoInteger(TERMINAL_BUILD),currency,DoubleToString(point,digits));
   return INIT_SUCCEEDED;
}

string Money(double value) { return DoubleToString(value,money_digits); }

bool Submit(const Signal &signal,const MqlTick &tick)
{
   if(!TesterOnly() || !ApprovedResearchReplay || OrdersTotal()!=0 || PositionsTotal()>1) return false;
   bool opening=signal.action=="ENTRY";
   if(opening==PositionSelect(_Symbol)) return true; // Explicit flat-only entry / positioned-only exit policy.
   if(PositionsTotal()!=(opening?0:1)) return false;
   MqlTradeRequest request={};
   MqlTradeResult result={};
   MqlTradeCheckResult check={};
   request.action=TRADE_ACTION_DEAL;
   request.symbol=_Symbol;
   request.type=(opening==(side=="BUY"))?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   request.price=request.type==ORDER_TYPE_BUY?tick.ask:tick.bid;
   request.volume=opening?volume:PositionGetDouble(POSITION_VOLUME);
   request.type_filling=ORDER_FILLING_FOK;
   double budget=MathMin(risk_cap,AccountInfoDouble(ACCOUNT_EQUITY)*risk_fraction);
   if(opening)
   {
      double pnl;
      if((side=="BUY" && !(stop<request.price && request.price<target))
         || (side=="SELL" && !(target<request.price && request.price<stop))
         || !OrderCalcProfit(request.type,_Symbol,volume,request.price,stop,pnl)
         || pnl>=0 || -pnl>budget) return false;
      request.sl=stop; request.tp=target;
   }
   else request.position=(ulong)PositionGetInteger(POSITION_TICKET);
   if(!OrderCheck(request,check) || !TesterOnly() || !OrderSend(request,result)
      || result.retcode!=TRADE_RETCODE_DONE || result.deal==0 || result.order==0
      || !HistoryDealSelect(result.deal)) return false;
   double risk=0;
   if(opening)
   {
      double pnl;
      if(!OrderCalcProfit(request.type,_Symbol,HistoryDealGetDouble(result.deal,DEAL_VOLUME),
                          HistoryDealGetDouble(result.deal,DEAL_PRICE),stop,pnl)
         || pnl>=0 || -pnl>budget) return false;
      risk=-pnl;
   }
   FileWrite(out,"ACTION",signal.index,result.deal,result.order,DoubleToString(request.price,digits),Money(risk));
   return true;
}

void OnTick()
{
   if(!TesterOnly() || failed || finished) return;
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) { failed=true; return; }
   long now=tick.time_msc-offset_ms;
   if(now<start_ms) return;
   if(!started)
   {
      if(now>=end_ms || PositionsTotal()!=0 || OrdersTotal()!=0) { failed=true; return; }
      started=true;
      FileWrite(out,"EQUITY",start_ms,Money(AccountInfoDouble(ACCOUNT_EQUITY)));
   }
   if(now<last_tick || tick.bid<=0 || tick.ask<tick.bid) { failed=true; return; }
   last_tick=now;
   bool triggered=false;
   while(cursor<ArraySize(schedule) && schedule[cursor].time<now)
   {
      Signal signal=schedule[cursor++];
      FileWrite(out,"SIGNAL",signal.index,signal.time/1000,signal.action,signal.triggered,now);
      if(signal.triggered==1 && signal.time<end_ms)
      {
         if(triggered || now>=end_ms || now-signal.time>max_delay || !Submit(signal,tick))
         { failed=true; return; }
         triggered=true;
      }
   }
   if(now>=end_ms)
   {
      if(PositionsTotal()!=0 || OrdersTotal()!=0 || cursor!=ArraySize(schedule)) { failed=true; return; }
      FileWrite(out,"EQUITY",end_ms,Money(AccountInfoDouble(ACCOUNT_EQUITY)));
      finished=true;
      return;
   }
   FileWrite(out,"EQUITY",now,Money(AccountInfoDouble(ACCOUNT_EQUITY)));
}

double OnTester()
{
   if(!TesterOnly() || failed || !finished ||
      !HistorySelect((datetime)((start_ms+offset_ms)/1000),(datetime)((end_ms+offset_ms)/1000))) return 0;
   for(int i=0;i<HistoryDealsTotal();i++)
   {
      ulong id=HistoryDealGetTicket(i);
      long stamp=HistoryDealGetInteger(id,DEAL_TIME_MSC);
      if(id==0) return 0;
      if(stamp-offset_ms<start_ms || stamp-offset_ms>=end_ms) continue;
      long type=HistoryDealGetInteger(id,DEAL_TYPE), entry=HistoryDealGetInteger(id,DEAL_ENTRY);
      long reason=HistoryDealGetInteger(id,DEAL_REASON);
      if((type!=DEAL_TYPE_BUY && type!=DEAL_TYPE_SELL) || (entry!=DEAL_ENTRY_IN && entry!=DEAL_ENTRY_OUT)
         || HistoryDealGetString(id,DEAL_SYMBOL)!=_Symbol) return 0;
      MqlTick quotes[];
      int n=CopyTicksRange(_Symbol,quotes,COPY_TICKS_ALL,(ulong)stamp,(ulong)stamp);
      if(n<1 || quotes[0].bid<=0 || quotes[0].ask<quotes[0].bid) return 0;
      for(int k=1;k<n;k++) if(quotes[k].bid!=quotes[0].bid || quotes[k].ask!=quotes[0].ask) return 0;
      FileWrite(out,"DEAL",id,HistoryDealGetInteger(id,DEAL_ORDER),HistoryDealGetInteger(id,DEAL_POSITION_ID),
         stamp-offset_ms,entry==DEAL_ENTRY_IN?"IN":"OUT",type==DEAL_TYPE_BUY?"BUY":"SELL",
         reason==DEAL_REASON_SL?"SL":reason==DEAL_REASON_TP?"TP":reason==DEAL_REASON_EXPERT?"RULE":"UNSUPPORTED",
         DoubleToString(HistoryDealGetDouble(id,DEAL_PRICE),digits),DoubleToString(HistoryDealGetDouble(id,DEAL_VOLUME),8),
         DoubleToString(quotes[0].bid,digits),DoubleToString(quotes[0].ask,digits),
         Money(HistoryDealGetDouble(id,DEAL_PROFIT)),Money(HistoryDealGetDouble(id,DEAL_COMMISSION)),
         Money(HistoryDealGetDouble(id,DEAL_SWAP)),Money(HistoryDealGetDouble(id,DEAL_FEE)));
   }
   FileWrite(out,"COMPLETE"); FileFlush(out);
   return 1;
}

void OnDeinit(const int reason) { if(out!=INVALID_HANDLE) FileClose(out); }
