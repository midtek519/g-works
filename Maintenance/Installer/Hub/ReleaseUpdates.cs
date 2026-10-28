using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net;
using System.Numerics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace GWorks {
 public sealed class UpdateNotice { public string Version; public string InstalledVersion; }
 public static class ReleaseUpdates {
  public const string CatalogueUrl="https://github.com/midtek519/g-works/releases/latest/download/public-catalogue-envelope.json";
  const int Limit=3000000;
  static JavaScriptSerializer Json { get {return new JavaScriptSerializer{MaxJsonLength=Limit};} }
  static Version ParseVersion(string text) {
   if(text==null||!Regex.IsMatch(text,@"^\d+\.\d+\.\d+$"))throw new InvalidDataException("Invalid release version.");
   return new Version(text);
  }
  static byte[] UnsignedBytes(string value) {
   var data=BigInteger.Parse(value).ToByteArray();Array.Reverse(data);
   if(data.Length>1&&data[0]==0){var trimmed=new byte[data.Length-1];Buffer.BlockCopy(data,1,trimmed,0,trimmed.Length);return trimmed;}
   return data;
  }
  // A verified catalogue is the only source of version notifications. No package
  // contents, URL commands, code or HTML from the service are executed here.
  public static UpdateNotice VerifyEnvelope(string envelope,string current,string keyJson) {
   return VerifyEnvelope(envelope,current,keyJson,null);
  }
  public static UpdateNotice VerifyEnvelope(string envelope,string current,string keyJson,string suite) {
   if(envelope==null||envelope.Length>Limit)throw new InvalidDataException("Release response is too large.");
   var outer=Json.Deserialize<Dictionary<string,object>>(envelope);
   var raw=Convert.FromBase64String(Convert.ToString(outer["catalogue"]));
   if(raw.Length>2000000)throw new InvalidDataException("Release catalogue is too large.");
   var signature=Convert.FromBase64String(Convert.ToString(outer["signature"]));
   var key=Json.Deserialize<Dictionary<string,object>>(keyJson);
   using(var rsa=new RSACryptoServiceProvider()){
    rsa.PersistKeyInCsp=false;
    rsa.ImportParameters(new RSAParameters{Modulus=UnsignedBytes(Convert.ToString(key["n"])),Exponent=UnsignedBytes(Convert.ToString(key["e"]))});
    if(rsa.KeySize<2048||!rsa.VerifyData(raw,CryptoConfig.MapNameToOID("SHA256"),signature))throw new InvalidDataException("Release catalogue signature is invalid.");
   }
   var catalogue=Json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(raw));
   if(Convert.ToInt32(catalogue["schema"])!=1||Convert.ToString(catalogue["channel"])!="public"||!catalogue.ContainsKey("packages"))throw new InvalidDataException("Unsupported public release catalogue.");
   if(suite=="professional")RequireProfessionalCatalogue(catalogue);
   else if(suite!=null)throw new InvalidDataException("This suite has no anonymous update feed.");
   string next=Convert.ToString(catalogue["release"]);
   return ParseVersion(next)>ParseVersion(current)?new UpdateNotice{Version=next,InstalledVersion=current}:null;
  }
  static bool Is(Dictionary<string,object> value,string name,string expected){object actual;return value.TryGetValue(name,out actual)&&actual is string&&String.Equals((string)actual,expected,StringComparison.Ordinal);}
  static bool NumberIs(Dictionary<string,object> value,string name,int expected){object actual;return value.TryGetValue(name,out actual)&&actual is int&&(int)actual==expected;}
  static void RequireProfessionalCatalogue(Dictionary<string,object> catalogue){
   if(!NumberIs(catalogue,"schema",1)||!NumberIs(catalogue,"suite_layout",1)||!NumberIs(catalogue,"distribution_policy",2)||!Is(catalogue,"suite","professional")||!Is(catalogue,"repository","midtek519/g-works"))throw new InvalidDataException("This signed catalogue is not compatible with the professional suite.");
   object activation;if(catalogue.TryGetValue("activation_service",out activation)&&(! (activation is string)||!String.IsNullOrEmpty((string)activation)))throw new InvalidDataException("Professional releases must not require an activation service.");
   object raw;var apps=catalogue.TryGetValue("applications",out raw)?raw as System.Collections.IList:null;
   if(apps==null||apps.Count!=3)throw new InvalidDataException("The professional application list is incomplete.");
   var expected=new Dictionary<string,string>{{"whiz","G-Whiz"},{"scope","G-Scope"},{"spot","G-Vault"}};var seen=new HashSet<string>();
   foreach(object row in apps){
    var app=row as Dictionary<string,object>;object ident;
    if(app==null||!app.TryGetValue("id",out ident)||!(ident is string)||!expected.ContainsKey((string)ident)||!seen.Add((string)ident)||!Is(app,"name",expected[(string)ident])||!Is(app,"suite","professional")||!Is(app,"visibility","public"))throw new InvalidDataException("The professional application list is incompatible.");
   }
   var packages=catalogue["packages"] as System.Collections.IList;if(packages==null)throw new InvalidDataException("The package list is invalid.");
   foreach(object row in packages){
    var package=row as Dictionary<string,object>;object app;
    if(package==null||(package.TryGetValue("app",out app)&&(!(app is string)||!expected.ContainsKey((string)app)))||Is(package,"id","gspot-launcher")||(Is(package,"kind","course")&&!Is(package,"app","whiz"))||(Is(package,"runtime_role","Launcher")&&!Is(package,"id","gworks-launcher")))throw new InvalidDataException("The package list crosses suite boundaries.");
   }
  }
  // Only the professional public repository supports anonymous update checks.
  // Private personal releases are obtained through their repository or bundle.
  public static string FeedForSuite(string suite){
   if(suite=="personal")return null;
   if(suite==null||suite=="professional")return CatalogueUrl;
   throw new InvalidDataException("Unknown suite installation.");
  }
  public static bool TryCachedNotice(string cacheJson,string current,string keyJson,string suite,DateTime now,out UpdateNotice notice){
   notice=null;
   try{
    string feed=FeedForSuite(suite);if(feed==null||cacheJson==null||cacheJson.Length>Limit)return false;
    var saved=Json.Deserialize<Dictionary<string,object>>(cacheJson);
    if(!NumberIs(saved,"schema",2)||!Is(saved,"suite",suite??"legacy")||!Is(saved,"feed",feed))return false;
    object timestamp,envelope;if(!saved.TryGetValue("checked_at",out timestamp)||!saved.TryGetValue("envelope",out envelope)||!(envelope is string))return false;
    DateTime checkedAt;if(!DateTime.TryParse(Convert.ToString(timestamp),CultureInfo.InvariantCulture,DateTimeStyles.RoundtripKind,out checkedAt))return false;
    TimeSpan elapsed=now.ToUniversalTime()-checkedAt.ToUniversalTime();if(elapsed<TimeSpan.Zero||elapsed>=TimeSpan.FromMinutes(10))return false;
    // A cached version is never trusted: recheck the signed payload, suite,
    // distribution policy and release version with the current bundled key.
    notice=VerifyEnvelope((string)envelope,current,keyJson,suite);return true;
   }catch{notice=null;return false;}
  }
  static string Download() {
   ServicePointManager.SecurityProtocol|=SecurityProtocolType.Tls12;
   var request=(HttpWebRequest)WebRequest.Create(CatalogueUrl);
   request.UserAgent="G-Works-Update-Check/1.0";request.Timeout=8000;request.ReadWriteTimeout=8000;
   using(var response=(HttpWebResponse)request.GetResponse()){
    if(response.ResponseUri.Scheme!="https"||response.ContentLength>Limit)throw new InvalidDataException("Invalid release response.");
    using(var stream=response.GetResponseStream())using(var buffer=new MemoryStream()){
     var bytes=new byte[16384];int count;
     while((count=stream.Read(bytes,0,bytes.Length))>0){if(buffer.Length+count>Limit)throw new InvalidDataException("Release response is too large.");buffer.Write(bytes,0,count);}
     return Encoding.UTF8.GetString(buffer.ToArray());
    }
   }
  }
  public static string InstallationSuite(string root){
   string suite=null;
   foreach(string filename in new[]{"installation.json","root.json"}){
    string path=Path.Combine(root,".gworks",filename);if(!File.Exists(path))continue;
    var record=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path));object value;
    if(record.TryGetValue("suite",out value)){
     string found=Convert.ToString(value);
     if(found!="personal"&&found!="professional")throw new InvalidDataException("Unknown suite installation.");
     if(suite!=null&&suite!=found)throw new InvalidDataException("Installation suite records disagree.");
     suite=found;
    }
   }
   return suite;
  }
  public static string MutexName(string root){
   using(var sha=SHA256.Create())return "Local\\GWorksReleaseCheck-"+BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(Path.GetFullPath(root).ToUpperInvariant()))).Replace("-","");
  }
  static void Report(Form owner,Action<string> callback,string message,Action<string,bool> onResult,bool available=false){
   if((callback==null&&onResult==null)||owner.IsDisposed||!owner.IsHandleCreated)return;
   try{owner.BeginInvoke(new Action(delegate{if(!owner.IsDisposed){if(callback!=null)callback(message);if(onResult!=null)onResult(message,available);}}));}catch{}
  }
  public static void CheckAsync(Form owner,string root,string installedVersion,Action<UpdateNotice> onAvailable,Action<string> onStatus=null,bool force=false) {
   CheckAsync(owner,root,installedVersion,onAvailable,onStatus,force,null);
  }
  public static void CheckAsync(Form owner,string root,string installedVersion,Action<UpdateNotice> onAvailable,Action<string> onStatus,bool force,Action<string,bool> onResult) {
   ThreadPool.QueueUserWorkItem(delegate {
    Mutex gate=null;bool acquired=false;
    try {
     string suite=InstallationSuite(root),feed=FeedForSuite(suite);
     if(feed==null){Report(owner,onStatus,"",onResult);return;}
     gate=new Mutex(false,MutexName(root));
     try{acquired=gate.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}
     if(!acquired){Report(owner,onStatus,"Another update check is running. Click to recheck.",onResult);return;}
     // An older launcher can coexist with newer installed apps. Prefer the
     // installation generation, so it never offers a downgrade.
     string record=Path.Combine(root,".gworks","installation.json");
     if(File.Exists(record)){
      var installed=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(record));
      if(installed.ContainsKey("release")){
       string known=Convert.ToString(installed["release"]);
       if(ParseVersion(known)>ParseVersion(installedVersion))installedVersion=known;
      }
     }
     string key;
     using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("gworks-public-key.json")){
      if(stream==null){Report(owner,onStatus,"Update verification unavailable. Click to retry.",onResult);return;}using(var reader=new StreamReader(stream))key=reader.ReadToEnd();
     }
     string cache=Path.Combine(root,".gworks","update-check.json");UpdateNotice notice=null;bool cached=false;
     if(!force&&File.Exists(cache)){
      try{cached=TryCachedNotice(File.ReadAllText(cache),installedVersion,key,suite,DateTime.UtcNow,out notice);}catch{}
     }
     if(!cached){
      string envelope=Download();notice=VerifyEnvelope(envelope,installedVersion,key,suite);
      try{Directory.CreateDirectory(Path.GetDirectoryName(cache));File.WriteAllText(cache,Json.Serialize(new{schema=2,suite=suite??"legacy",feed=feed,checked_at=DateTime.UtcNow.ToString("o"),envelope=envelope}));}catch{}
     }
     if(notice!=null&&(owner.IsDisposed||!owner.IsHandleCreated))return;
     Report(owner,onStatus,notice==null?"G-Works is up to date. Click to recheck.":"G-Works "+notice.Version+" is available. Use Install / update.",onResult,notice!=null);
     if(notice!=null)owner.BeginInvoke(new Action(delegate{if(!owner.IsDisposed)onAvailable(notice);}));
    } catch {Report(owner,onStatus,"Could not check for updates. Click to retry.",onResult);}
    finally{if(gate!=null){if(acquired)gate.ReleaseMutex();gate.Dispose();}}
   });
  }
  // Shared entry for desktop modules launched directly, without the hub.
  public static void CheckAndPromptAsync(Form owner,string root,string installedVersion){
   CheckAsync(owner,root,installedVersion,delegate(UpdateNotice notice){
    if(MessageBox.Show(owner,"G-Works "+notice.Version+" is available. Open Install / update now?","G-Works update",MessageBoxButtons.YesNo,MessageBoxIcon.Information)!=DialogResult.Yes)return;
    try{
     string setup=Path.Combine(root,"Install G-Works.exe");
     if(!File.Exists(setup))throw new FileNotFoundException("Open the G-Works folder and download its current installer.");
     Process.Start(new ProcessStartInfo(setup){WorkingDirectory=root,UseShellExecute=true});
    }catch(Exception error){MessageBox.Show(owner,error.Message,"G-Works update",MessageBoxButtons.OK,MessageBoxIcon.Information);}
   });
  }
 }
}
