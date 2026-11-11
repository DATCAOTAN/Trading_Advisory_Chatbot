// Research-only decimal arithmetic: 28 significant digits, half-even operations.
// Empty string is an invalid/unsupported value, never a substituted zero.
string PTrim(string a)
{
   while(StringLen(a)>1 && StringSubstr(a,0,1)=="0") a=StringSubstr(a,1);
   return a;
}
string PZeros(int n)
{
   string s=""; for(int i=0;i<n;i++) s+="0"; return s;
}
int PCmp(string a,string b)
{
   a=PTrim(a); b=PTrim(b);
   if(StringLen(a)!=StringLen(b)) return StringLen(a)>StringLen(b)?1:-1;
   return StringCompare(a,b);
}
string PAdd(string a,string b)
{
   string out=""; int carry=0,i=StringLen(a)-1,j=StringLen(b)-1;
   while(i>=0 || j>=0 || carry>0)
   {
      int n=carry;
      if(i>=0) n+=(int)StringGetCharacter(a,i--)-48;
      if(j>=0) n+=(int)StringGetCharacter(b,j--)-48;
      out=IntegerToString(n%10)+out; carry=n/10;
   }
   return PTrim(out);
}
string PSub(string a,string b)
{
   string out=""; int borrow=0,j=StringLen(b)-1;
   for(int i=StringLen(a)-1;i>=0;i--)
   {
      int n=(int)StringGetCharacter(a,i)-48-borrow;
      if(j>=0) n-=(int)StringGetCharacter(b,j--)-48;
      borrow=n<0?1:0; if(n<0) n+=10;
      out=IntegerToString(n)+out;
   }
   return PTrim(out);
}
string PMul(string a,string b)
{
   string out="0";
   for(int i=0;i<StringLen(b);i++)
   {
      out+="0";
      int digit=(int)StringGetCharacter(b,i)-48;
      for(int j=0;j<digit;j++) out=PAdd(out,a);
   }
   return PTrim(out);
}
string PDiv(string a,string b,string &remainder)
{
   string out=""; remainder="0";
   for(int i=0;i<StringLen(a);i++)
   {
      remainder=PTrim(remainder+StringSubstr(a,i,1)); int digit=0;
      while(PCmp(remainder,b)>=0) { remainder=PSub(remainder,b); digit++; }
      out+=IntegerToString(digit);
   }
   return PTrim(out);
}
bool DParts(string text,string &digits,int &exponent,bool &negative)
{
   if(text=="" || StringLen(text)>160) return false;
   negative=StringSubstr(text,0,1)=="-";
   if(negative || StringSubstr(text,0,1)=="+") text=StringSubstr(text,1);
   int e=StringFind(text,"e"); if(e<0) e=StringFind(text,"E");
   exponent=0;
   if(e>=0)
   {
      string power=StringSubstr(text,e+1); text=StringSubstr(text,0,e);
      int start=(StringSubstr(power,0,1)=="-" || StringSubstr(power,0,1)=="+")?1:0;
      if(StringLen(power)<=start || StringLen(power)>4) return false;
      for(int i=start;i<StringLen(power);i++)
         if(StringGetCharacter(power,i)<48 || StringGetCharacter(power,i)>57) return false;
      exponent=(int)StringToInteger(power);
   }
   digits=""; bool point=false;
   for(int i=0;i<StringLen(text);i++)
   {
      ushort c=StringGetCharacter(text,i);
      if(c==46 && !point) { point=true; continue; }
      if(c<48 || c>57) return false;
      digits+=StringSubstr(text,i,1); if(point) exponent--;
   }
   digits=PTrim(digits);
   return digits!="" && StringLen(digits)<=128 && exponent>=-64 && exponent<=64;
}
string DPack(string digits,int exponent,bool negative,bool rounded=true,bool sticky=false)
{
   digits=PTrim(digits);
   int extra=StringLen(digits)-28;
   if(rounded && extra>0)
   {
      string tail=StringSubstr(digits,28); digits=StringSubstr(digits,0,28);
      int first=(int)StringGetCharacter(tail,0)-48;
      bool rest=sticky || PTrim(StringSubstr(tail,1))!="0" && StringLen(tail)>1;
      if(first>5 || (first==5 && (rest || ((int)StringGetCharacter(digits,27)-48)%2==1)))
         digits=PAdd(digits,"1");
      exponent+=extra;
   }
   while(StringLen(digits)>1 && StringSubstr(digits,StringLen(digits)-1)=="0")
      { digits=StringSubstr(digits,0,StringLen(digits)-1); exponent++; }
   if(exponent < -64 || exponent>64 || StringLen(digits)>128) return "";
   if(digits=="0") return "0";
   return (negative?"-":"")+digits+"e"+IntegerToString(exponent);
}
string DRead(string text)
{
   string digits; int exponent; bool negative;
   if(!DParts(text,digits,exponent,negative)) return "";
   return DPack(digits,exponent,negative,false);
}
string DFloat(double value)
{
   if(!MathIsValidNumber(value)) return "";
   // Match Python's shortest decimal round-trip, not a fixed decimal truncation.
   for(int precision=1;precision<=17;precision++)
   {
      string text=StringFormat("%."+IntegerToString(precision)+"g",value);
      if(StringToDouble(text)==value) return DRead(text);
   }
   return "";
}
string DNeg(string a)
{
   if(a=="" || a=="0") return a;
   return StringSubstr(a,0,1)=="-"?StringSubstr(a,1):"-"+a;
}
string DAdd(string a,string b)
{
   string x,y; int ex,ey; bool nx,ny;
   if(!DParts(a,x,ex,nx) || !DParts(b,y,ey,ny)) return "";
   int exponent=(int)MathMin(ex,ey);
   x+=PZeros(ex-exponent); y+=PZeros(ey-exponent);
   if(StringLen(x)>128 || StringLen(y)>128) return "";
   if(nx==ny) return DPack(PAdd(x,y),exponent,nx);
   return PCmp(x,y)>=0?DPack(PSub(x,y),exponent,nx):DPack(PSub(y,x),exponent,ny);
}
string DSub(string a,string b) { return DAdd(a,DNeg(b)); }
string DMul(string a,string b)
{
   string x,y; int ex,ey; bool nx,ny;
   if(!DParts(a,x,ex,nx) || !DParts(b,y,ey,ny) || StringLen(x)+StringLen(y)>128) return "";
   return DPack(PMul(x,y),ex+ey,nx!=ny);
}
string DDiv(string a,string b)
{
   string x,y; int ex,ey; bool nx,ny;
   if(!DParts(a,x,ex,nx) || !DParts(b,y,ey,ny) || y=="0") return "";
   int shift=29+StringLen(y)-StringLen(x);
   if(shift>=0) x+=PZeros(shift); else y+=PZeros(-shift);
   if(StringLen(x)>128 || StringLen(y)>128) return "";
   string remainder,quotient=PDiv(x,y,remainder);
   return DPack(quotient,ex-ey-shift,nx!=ny,true,remainder!="0");
}
int DCmp(string a,string b)
{
   string difference=DSub(a,b),digits; int exponent; bool negative;
   if(!DParts(difference,digits,exponent,negative)) return 99;
   return digits=="0"?0:(negative?-1:1);
}
string DMin(string a,string b)
{
   if(a=="" || b=="") return "";
   return DCmp(a,b)<=0?a:b;
}
string DIntegral(string a,bool half_up)
{
   string digits; int exponent; bool negative;
   if(!DParts(a,digits,exponent,negative)) return "";
   if(exponent>=0) return a;
   int keep=StringLen(digits)+exponent;
   string whole=keep>0?StringSubstr(digits,0,keep):"0";
   if(half_up && keep>=0 && StringGetCharacter(digits,keep)>=53) whole=PAdd(whole,"1");
   return DPack(whole,0,negative);
}
string DTick(string price,string tick)
{
   if(DCmp(tick,"0")<=0) return "";
   return DMul(DIntegral(DDiv(price,tick),true),tick);
}
