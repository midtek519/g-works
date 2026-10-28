using System;
using System.Numerics;
using System.Text.RegularExpressions;
namespace GWorks {
 public sealed class SemVersion:IComparable<SemVersion> {
  public readonly string Text,Prerelease;readonly BigInteger[] numbers;
  static readonly Regex Pattern=new Regex(@"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$");
  public SemVersion(string text){var m=Pattern.Match(text??"");if(!m.Success)throw new FormatException("Invalid semantic version.");Text=text;Prerelease=m.Groups[4].Value;numbers=new[]{BigInteger.Parse(m.Groups[1].Value),BigInteger.Parse(m.Groups[2].Value),BigInteger.Parse(m.Groups[3].Value)};foreach(string p in Prerelease.Split('.'))if(Regex.IsMatch(p,@"^[0-9]+$")&&p.Length>1&&p[0]=='0')throw new FormatException("Invalid prerelease identifier.");}
  public string Display {get{return Prerelease.StartsWith("beta.",StringComparison.Ordinal)?"Beta "+Prerelease.Substring(5):"Version "+Text;}}
  public string Epoch {get{var p=Prerelease.Split('.');return Prerelease.Length==0?"stable-"+numbers[0]:p.Length>1&&Regex.IsMatch(p[1],@"^[0-9]+$")?p[0].ToLowerInvariant()+"-"+p[1]:"prerelease-"+numbers[0]+"."+numbers[1]+"."+numbers[2];}}
  public int CompareTo(SemVersion other){for(int i=0;i<3;i++){int c=numbers[i].CompareTo(other.numbers[i]);if(c!=0)return c;}if(Prerelease.Length==0||other.Prerelease.Length==0)return Prerelease.Length==other.Prerelease.Length?0:Prerelease.Length==0?1:-1;var left=Prerelease.Split('.');var right=other.Prerelease.Split('.');for(int i=0;i<Math.Min(left.Length,right.Length);i++){BigInteger a,b;bool an=BigInteger.TryParse(left[i],out a)&&Regex.IsMatch(left[i],@"^[0-9]+$");bool bn=BigInteger.TryParse(right[i],out b)&&Regex.IsMatch(right[i],@"^[0-9]+$");int c=an&&bn?a.CompareTo(b):an!=bn?(an?-1:1):String.CompareOrdinal(left[i],right[i]);if(c!=0)return c;}return left.Length.CompareTo(right.Length);}
  public static bool operator >(SemVersion a,SemVersion b){return a.CompareTo(b)>0;}public static bool operator <(SemVersion a,SemVersion b){return a.CompareTo(b)<0;}
 }
}
