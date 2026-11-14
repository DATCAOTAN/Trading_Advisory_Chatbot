#property strict
#property service
#property version "1.30"
#include "G4ImportPins.mqh"

input bool ApproveImport=false;
const string folder=G4_INPUT_FOLDER;

bool Pin(string file,string expected)
{
   int f=FileOpen(folder+file,FILE_READ|FILE_BIN);
   if(f==INVALID_HANDLE) return false;
   long size=(long)FileSize(f);
   if(size<=0 || size>12000000) { FileClose(f); return false; }
   uchar content[],key[],digest[];
   bool read=(FileReadArray(f,content,0,(int)size)==size);
   FileClose(f);
   if(!read || CryptEncode(CRYPT_HASH_SHA256,content,key,digest)!=32) return false;
   string hex="";
   for(int i=0;i<32;i++) hex+=StringFormat("%02x",digest[i]);
   return hex==expected;
}

bool ReadBars(MqlRates &bars[])
{
   int f=FileOpen(folder+"bars.tsv",FILE_READ|FILE_CSV|FILE_ANSI,'\t');
   if(f==INVALID_HANDLE) return false;
   for(int j=0;j<9;j++) FileReadString(f);
   ArrayResize(bars,G4_BARS);
   for(int i=0;i<G4_BARS;i++)
   {
      string date=FileReadString(f),time=FileReadString(f);
      bars[i].time=StringToTime(date+" "+time);
      bars[i].open=StringToDouble(FileReadString(f)); bars[i].high=StringToDouble(FileReadString(f));
      bars[i].low=StringToDouble(FileReadString(f)); bars[i].close=StringToDouble(FileReadString(f));
      bars[i].tick_volume=StringToInteger(FileReadString(f)); bars[i].real_volume=StringToInteger(FileReadString(f));
      bars[i].spread=(int)StringToInteger(FileReadString(f));
      if(bars[i].time<=0 || bars[i].time%60!=0 || (i>0 && bars[i].time!=bars[i-1].time+60))
      { FileClose(f); return false; }
   }
   bool ending=FileIsEnding(f); FileClose(f); return ending;
}

bool ReadTicks(MqlTick &ticks[])
{
   int f=FileOpen(folder+"ticks.tsv",FILE_READ|FILE_CSV|FILE_ANSI,'\t');
   if(f==INVALID_HANDLE) return false;
   for(int j=0;j<6;j++) FileReadString(f);
   ArrayResize(ticks,G4_TICKS);
   for(int i=0;i<G4_TICKS;i++)
   {
      string date=FileReadString(f),time=FileReadString(f);
      ticks[i].time=StringToTime(date+" "+StringSubstr(time,0,8));
      ticks[i].time_msc=1000*(long)ticks[i].time+StringToInteger(StringSubstr(time,9,3));
      ticks[i].bid=StringToDouble(FileReadString(f)); ticks[i].ask=StringToDouble(FileReadString(f));
      ticks[i].last=StringToDouble(FileReadString(f));
      ticks[i].volume=(ulong)StringToInteger(FileReadString(f)); ticks[i].volume_real=0;
      // Import representation only: original archive flags are retained separately, not claimed equal.
      ticks[i].flags=TICK_FLAG_BID|TICK_FLAG_ASK;
      if(ticks[i].last>0) ticks[i].flags|=TICK_FLAG_LAST;
      if(ticks[i].time<=0 || ticks[i].bid<=0 || ticks[i].ask<ticks[i].bid || ticks[i].volume!=0
         || (i>0 && ticks[i].time_msc<ticks[i-1].time_msc)) { FileClose(f); return false; }
   }
   bool ending=FileIsEnding(f); FileClose(f); return ending;
}

bool SetIntegerProperty(ENUM_SYMBOL_INFO_INTEGER property,long value)
{
   ResetLastError();
   bool ok=CustomSymbolSetInteger(G4_SYMBOL,property,value);
   int error=GetLastError();
   if(!ok) PrintFormat("G4_CONFIG_FAIL api=CustomSymbolSetInteger symbol=%s property=%s value=%I64d error=%d",
      G4_SYMBOL,EnumToString(property),value,error);
   return ok;
}

bool SetDoubleProperty(ENUM_SYMBOL_INFO_DOUBLE property,double value)
{
   ResetLastError();
   bool ok=CustomSymbolSetDouble(G4_SYMBOL,property,value);
   int error=GetLastError();
   if(!ok) PrintFormat("G4_CONFIG_FAIL api=CustomSymbolSetDouble symbol=%s property=%s value=%.17g error=%d",
      G4_SYMBOL,EnumToString(property),value,error);
   return ok;
}

bool SetStringProperty(ENUM_SYMBOL_INFO_STRING property,string value)
{
   ResetLastError();
   bool ok=CustomSymbolSetString(G4_SYMBOL,property,value);
   int error=GetLastError();
   if(!ok) PrintFormat("G4_CONFIG_FAIL api=CustomSymbolSetString symbol=%s property=%s value=%s error=%d",
      G4_SYMBOL,EnumToString(property),value,error);
   return ok;
}

bool CheckIntegerProperty(ENUM_SYMBOL_INFO_INTEGER property,long expected)
{
   long actual=0;
   ResetLastError();
   bool ok=SymbolInfoInteger(G4_SYMBOL,property,actual);
   int error=GetLastError();
   bool match=ok && actual==expected;
   PrintFormat("G4_CONFIG_READBACK api=SymbolInfoInteger property=%s expected=%I64d actual=%I64d read_ok=%d match=%d error=%d",
      EnumToString(property),expected,actual,(int)ok,(int)match,error);
   return match;
}

bool CheckDoubleProperty(ENUM_SYMBOL_INFO_DOUBLE property,double expected)
{
   double actual=0;
   ResetLastError();
   bool ok=SymbolInfoDouble(G4_SYMBOL,property,actual);
   int error=GetLastError();
   bool match=ok && actual==expected;
   PrintFormat("G4_CONFIG_READBACK api=SymbolInfoDouble property=%s expected=%.17g actual=%.17g read_ok=%d match=%d error=%d",
      EnumToString(property),expected,actual,(int)ok,(int)match,error);
   return match;
}

bool CheckStringProperty(ENUM_SYMBOL_INFO_STRING property,string expected)
{
   string actual="";
   ResetLastError();
   bool ok=SymbolInfoString(G4_SYMBOL,property,actual);
   int error=GetLastError();
   bool match=ok && actual==expected;
   PrintFormat("G4_CONFIG_READBACK api=SymbolInfoString property=%s expected=%s actual=%s read_ok=%d match=%d error=%d",
      EnumToString(property),expected,actual,(int)ok,(int)match,error);
   return match;
}

void LogCreationDefaults()
{
   ENUM_SYMBOL_INFO_DOUBLE doubles[]={SYMBOL_VOLUME_MAX,SYMBOL_VOLUME_MIN,SYMBOL_VOLUME_STEP,SYMBOL_POINT};
   for(int i=0;i<ArraySize(doubles);i++)
   {
      double value=0;
      ResetLastError();
      bool ok=SymbolInfoDouble(G4_SYMBOL,doubles[i],value);
      int error=GetLastError();
      PrintFormat("G4_CONFIG_DEFAULT api=SymbolInfoDouble property=%s value=%.17g read_ok=%d error=%d",
         EnumToString(doubles[i]),value,(int)ok,error);
   }
   ENUM_SYMBOL_INFO_INTEGER integers[]={SYMBOL_DIGITS,SYMBOL_TRADE_CALC_MODE};
   for(int i=0;i<ArraySize(integers);i++)
   {
      long value=0;
      ResetLastError();
      bool ok=SymbolInfoInteger(G4_SYMBOL,integers[i],value);
      int error=GetLastError();
      PrintFormat("G4_CONFIG_DEFAULT api=SymbolInfoInteger property=%s value=%I64d read_ok=%d error=%d",
         EnumToString(integers[i]),value,(int)ok,error);
   }
   ENUM_SYMBOL_INFO_STRING strings[]={SYMBOL_CURRENCY_BASE,SYMBOL_CURRENCY_PROFIT,SYMBOL_CURRENCY_MARGIN};
   for(int i=0;i<ArraySize(strings);i++)
   {
      string value="";
      ResetLastError();
      bool ok=SymbolInfoString(G4_SYMBOL,strings[i],value);
      int error=GetLastError();
      PrintFormat("G4_CONFIG_DEFAULT api=SymbolInfoString property=%s value=%s read_ok=%d error=%d",
         EnumToString(strings[i]),value,(int)ok,error);
   }
}

bool VerifyConfiguration()
{
   bool ok=true;
   // Only quote representation, safety and provenance gate the historical-data roundtrip.
   if(!CheckIntegerProperty(SYMBOL_DIGITS,3)) ok=false;
   if(!CheckIntegerProperty(SYMBOL_CHART_MODE,SYMBOL_CHART_MODE_BID)) ok=false;
   if(!CheckIntegerProperty(SYMBOL_TRADE_MODE,SYMBOL_TRADE_MODE_DISABLED)) ok=false;
   if(!CheckDoubleProperty(SYMBOL_POINT,0.001)) ok=false;
   if(!CheckDoubleProperty(SYMBOL_TRADE_TICK_SIZE,0.001)) ok=false;
   if(!CheckStringProperty(SYMBOL_DESCRIPTION,"G4 CAPTURE ONLY; CURRENT metadata; historical swap UNKNOWN")) ok=false;
   bool financial_ok=true;
   if(!CheckIntegerProperty(SYMBOL_TRADE_CALC_MODE,SYMBOL_CALC_MODE_FOREX)) financial_ok=false;
   if(!CheckDoubleProperty(SYMBOL_TRADE_TICK_VALUE,0.1)) financial_ok=false;
   if(!CheckDoubleProperty(SYMBOL_TRADE_CONTRACT_SIZE,100)) financial_ok=false;
   if(!CheckDoubleProperty(SYMBOL_VOLUME_MAX,200)) financial_ok=false;
   if(!CheckDoubleProperty(SYMBOL_VOLUME_STEP,0.01)) financial_ok=false;
   if(!CheckDoubleProperty(SYMBOL_VOLUME_MIN,0.01)) financial_ok=false;
   if(!CheckStringProperty(SYMBOL_CURRENCY_BASE,"XAU")) financial_ok=false;
   if(!CheckStringProperty(SYMBOL_CURRENCY_PROFIT,"USD")) financial_ok=false;
   if(!CheckStringProperty(SYMBOL_CURRENCY_MARGIN,"XAU")) financial_ok=false;
   PrintFormat("G4_FINANCIAL_CONFIGURATION snapshot_match=%d status=%s; historical specifications/swap NOT_CERTIFIED; no financial/Tester acceptance",
      (int)financial_ok,financial_ok ? "NOT_CERTIFIED" : "BLOCKED");
   for(int day=0;day<7;day++)
   {
      bool required=(G4_QUOTE_DAYS_MASK & (1<<day))!=0;
      datetime from=0,to=0;
      ResetLastError();
      bool read=SymbolInfoSessionQuote(G4_SYMBOL,(ENUM_DAY_OF_WEEK)day,0,from,to);
      int error=GetLastError();
      bool match=read && from==0 && to==86400;
      PrintFormat("G4_CONFIG_READBACK api=SymbolInfoSessionQuote day=%d required=%d session=0 expected_from=0 expected_to=86400 actual_from=%I64d actual_to=%I64d read_ok=%d match=%d error=%d",
         day,(int)required,(long)from,(long)to,(int)read,(int)match,error);
      if(required && !match) ok=false;
   }
   if(ok) Print("G4_DATA_CONFIGURATION_READBACK_MATCH; required quote days only; financial fidelity NOT_CERTIFIED");
   return ok;
}

bool Configure()
{
   // Set history-clearing properties before importing; never clone a broker profile.
   if(!SetIntegerProperty(SYMBOL_DIGITS,3)) return false;
   if(!SetIntegerProperty(SYMBOL_CHART_MODE,SYMBOL_CHART_MODE_BID)) return false;
   if(!SetIntegerProperty(SYMBOL_TRADE_MODE,SYMBOL_TRADE_MODE_DISABLED)) return false;
   if(!SetIntegerProperty(SYMBOL_TRADE_CALC_MODE,SYMBOL_CALC_MODE_FOREX)) return false;
   if(!SetDoubleProperty(SYMBOL_POINT,0.001)) return false;
   if(!SetDoubleProperty(SYMBOL_TRADE_TICK_SIZE,0.001)) return false;
   if(!SetDoubleProperty(SYMBOL_TRADE_TICK_VALUE,0.1)) return false;
   if(!SetDoubleProperty(SYMBOL_TRADE_CONTRACT_SIZE,100)) return false;
   // Establish the upper bound and granularity before lowering the minimum; values remain pinned.
   if(!SetDoubleProperty(SYMBOL_VOLUME_MAX,200)) return false;
   if(!SetDoubleProperty(SYMBOL_VOLUME_STEP,0.01)) return false;
   if(!SetDoubleProperty(SYMBOL_VOLUME_MIN,0.01)) return false;
   // Platform-derived currencies are observed separately, never rewritten to force snapshot equality.
   if(!SetStringProperty(SYMBOL_DESCRIPTION,"G4 CAPTURE ONLY; CURRENT metadata; historical swap UNKNOWN")) return false;
   for(int day=0;day<7;day++)
   {
      if((G4_QUOTE_DAYS_MASK & (1<<day))==0) continue;
      ResetLastError();
      bool ok=CustomSymbolSetSessionQuote(G4_SYMBOL,(ENUM_DAY_OF_WEEK)day,0,0,86400);
      int error=GetLastError();
      if(!ok) { PrintFormat("G4_CONFIG_FAIL api=CustomSymbolSetSessionQuote symbol=%s day=%d session=0 from=0 to=86400 error=%d",
         G4_SYMBOL,day,error); return false; }
   }
   return true;
}

bool Roundtrip(MqlRates &bars[],MqlTick &ticks[])
{
   MqlRates actual_bars[]; MqlTick actual_ticks[];
   ArraySetAsSeries(actual_bars,false); ArraySetAsSeries(actual_ticks,false);
   // Query the entire custom history, not only requested rows: unexpected extras must fail.
   ResetLastError();
   int nb=CopyRates(G4_SYMBOL,PERIOD_M1,(datetime)0,(datetime)32503680000,actual_bars);
   int bars_error=GetLastError();
   ResetLastError();
   int nt=CopyTicksRange(G4_SYMBOL,actual_ticks,COPY_TICKS_ALL,0,(ulong)LONG_MAX);
   int ticks_error=GetLastError();
   if(nb!=G4_BARS || nt!=G4_TICKS) { PrintFormat("G4_IMPORT_FAIL readback bars=%d expected=%d error=%d ticks=%d expected=%d error=%d",
      nb,G4_BARS,bars_error,nt,G4_TICKS,ticks_error); return false; }
   for(int i=0;i<nb;i++)
      if(actual_bars[i].time!=bars[i].time || actual_bars[i].open!=bars[i].open || actual_bars[i].high!=bars[i].high
         || actual_bars[i].low!=bars[i].low || actual_bars[i].close!=bars[i].close
         || actual_bars[i].tick_volume!=bars[i].tick_volume || actual_bars[i].real_volume!=bars[i].real_volume
         || actual_bars[i].spread!=bars[i].spread) { PrintFormat("G4_IMPORT_FAIL bar index=%d",i); return false; }
   int flag_changes=0,volume_changes=0;
   for(int i=0;i<nt;i++)
   {
      if(actual_ticks[i].time!=ticks[i].time || actual_ticks[i].time_msc!=ticks[i].time_msc
         || actual_ticks[i].bid!=ticks[i].bid || actual_ticks[i].ask!=ticks[i].ask || actual_ticks[i].last!=ticks[i].last)
      { PrintFormat("G4_IMPORT_FAIL tick index=%d",i); return false; }
      if(actual_ticks[i].flags!=ticks[i].flags) flag_changes++;
      if(actual_ticks[i].volume!=ticks[i].volume || actual_ticks[i].volume_real!=ticks[i].volume_real) volume_changes++;
   }
   string output=folder+"roundtrip.csv";
   if(FileIsExist(output)) { Print("G4_IMPORT_FAIL output exists; preserve evidence"); return false; }
   int f=FileOpen(output,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(f==INVALID_HANDLE) return false;
   FileWrite(f,"G4_IMPORT_ROUNDTRIP",G4_SYMBOL,"SHIFT_0",(int)TerminalInfoInteger(TERMINAL_BUILD));
   for(int i=0;i<nt;i++) FileWrite(f,"TICK",i,actual_ticks[i].time,actual_ticks[i].time_msc,
      DoubleToString(actual_ticks[i].bid,3),DoubleToString(actual_ticks[i].ask,3),DoubleToString(actual_ticks[i].last,3),
      actual_ticks[i].flags,actual_ticks[i].volume,actual_ticks[i].volume_real);
   FileWrite(f,"MATCH",nb,nt,"FLAGS_NOT_SOURCE_EQUALITY",flag_changes,"VOLUME_UNAVAILABLE_PADDING",volume_changes);
   FileClose(f);
   PrintFormat("G4_IMPORT_ROUNDTRIP_PASS bars=%d ticks=%d; flags/volume NOT original equality; no financial certification",nb,nt);
   return true;
}

void OnStart()
{
   PrintFormat("G4_IMPORT_SOURCE sha256=%s symbol=%s configuration_only=%d bars_pin=%s ticks_pin=%s",
      G4_IMPORT_SOURCE_SHA256,G4_SYMBOL,(int)G4_CONFIGURATION_ONLY,G4_BAR_PIN,G4_TICK_PIN);
   if(MQLInfoInteger(MQL_TESTER) || TerminalInfoInteger(TERMINAL_CONNECTED)
      || TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || TerminalInfoInteger(TERMINAL_COMMUNITY_ACCOUNT)
      || AccountInfoInteger(ACCOUNT_LOGIN)!=0) { Print("G4_IMPORT_FAIL offline credential-free research terminal required"); return; }
   if(!Pin("bars.tsv",G4_BAR_PIN) || !Pin("ticks.tsv",G4_TICK_PIN)) { Print("G4_IMPORT_FAIL input hash"); return; }
   MqlRates bars[]; MqlTick ticks[];
   if(!ReadBars(bars) || !ReadTicks(ticks)) { Print("G4_IMPORT_FAIL schema/order"); return; }
   if(G4_QUOTE_DAYS_MASK<=0 || G4_QUOTE_DAYS_MASK>127) { Print("G4_IMPORT_FAIL quote day mask"); return; }
   // Bind session scope to all actual records, including pre-start bars and boundary ticks.
   MqlDateTime stamp;
   int observed_days=0;
   for(int i=0;i<G4_BARS;i++)
   {
      if(!TimeToStruct(bars[i].time,stamp)) { Print("G4_IMPORT_FAIL bar quote day unavailable"); return; }
      observed_days|=(1<<stamp.day_of_week);
   }
   for(int i=0;i<G4_TICKS;i++)
   {
      if(!TimeToStruct(ticks[i].time,stamp)) { Print("G4_IMPORT_FAIL tick quote day unavailable"); return; }
      observed_days|=(1<<stamp.day_of_week);
   }
   if(observed_days!=G4_QUOTE_DAYS_MASK) { Print("G4_IMPORT_FAIL quote day scope mismatch"); return; }
   bool custom=false;
   if(SymbolExist(G4_SYMBOL,custom))
   {
      if(!custom) { Print("G4_IMPORT_FAIL broker symbol collision"); return; }
      // Existing history is verification-only, including a partial failed import. Never overwrite it.
      if(G4_CONFIGURATION_ONLY) { Print("G4_CONFIG_TARGET_EXISTS_READ_ONLY; choose a separately pinned fresh target"); return; }
   }
   else
   {
      if(!ApproveImport) { Print("G4_IMPORT_APPROVAL_REQUIRED"); return; }
      ResetLastError();
      bool created=CustomSymbolCreate(G4_SYMBOL,"G4Research");
      int create_error=GetLastError();
      if(!created) { PrintFormat("G4_IMPORT_FAIL api=CustomSymbolCreate symbol=%s error=%d",G4_SYMBOL,create_error); return; }
      // Property getters can require Market Watch selection; select only this newly created research symbol.
      ResetLastError();
      bool selected=SymbolSelect(G4_SYMBOL,true);
      int select_error=GetLastError();
      if(!selected) { PrintFormat("G4_IMPORT_FAIL api=SymbolSelect symbol=%s error=%d",G4_SYMBOL,select_error); return; }
      // Defaults are observations; required post-configuration getters enforce the data gate.
      LogCreationDefaults();
      if(!Configure()) { VerifyConfiguration(); Print("G4_IMPORT_STOP configuration failed; no data imported; preserve target"); return; }
      if(!VerifyConfiguration()) { Print("G4_IMPORT_STOP configuration readback failed; preserve target; no retry"); return; }
      if(G4_CONFIGURATION_ONLY) { Print("G4_CONFIGURATION_ONLY_COMPLETE; no bars/ticks imported; not a round-trip PASS"); return; }
      ResetLastError();
      int written_ticks=CustomTicksReplace(G4_SYMBOL,ticks[0].time_msc,ticks[G4_TICKS-1].time_msc,ticks);
      int tick_error=GetLastError();
      if(written_ticks!=G4_TICKS) { PrintFormat("G4_IMPORT_FAIL api=CustomTicksReplace count=%d expected=%d error=%d",
         written_ticks,G4_TICKS,tick_error); return; }
      ResetLastError();
      int written_bars=CustomRatesReplace(G4_SYMBOL,bars[0].time,bars[G4_BARS-1].time,bars);
      int bar_error=GetLastError();
      if(written_bars!=G4_BARS) { PrintFormat("G4_IMPORT_FAIL api=CustomRatesReplace count=%d expected=%d error=%d",
         written_bars,G4_BARS,bar_error); return; }
   }
   if(!SymbolSelect(G4_SYMBOL,true)) { Print("G4_IMPORT_FAIL select"); return; }
   if(!VerifyConfiguration()) { Print("G4_IMPORT_FAIL custom specification readback mismatch"); return; }
   if(!Roundtrip(bars,ticks)) PrintFormat("G4_IMPORT_INCONCLUSIVE error=%d; no Tester authorization",GetLastError());
}
