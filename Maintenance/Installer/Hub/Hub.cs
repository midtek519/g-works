using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
namespace GWorks {
 class AppChoice {public string Id,Name,Folder,Description,Color,SecondaryId,SecondaryLabel,Icon;}
 class Target {public string File,Arguments,Directory;public bool Shell;}
 class CompanionChoice {public string id,label,parent,description,icon;}
 class LauncherAction {public string Id,Label,Icon,UnavailableLabel;}
 class LauncherProfile {
  public virtual string Name {get{return "G-Works";}}
  public virtual string Icon {get{return "g-works";}}
  public virtual AppChoice[] Apps {get{return new[]{
   new AppChoice{Id="whiz",Name="G-Whiz",Folder="G-Whiz",Description="Courses, questions & teaching materials",Color="#B72D49",Icon="g-whiz",SecondaryId="course-organizer",SecondaryLabel="G-View"},
   new AppChoice{Id="scope",Name="G-Scope",Folder="G-Scope",Description="Scans, rubrics & grading",Color="#A96A13",Icon="g-scope",SecondaryId="rubric-lens",SecondaryLabel="G-Rater"},
   new AppChoice{Id="spot",Name="G-Vault",Folder="G-Vault",Description="Grades, letters & integrity records",Color="#245FB6",Icon="g-vault",SecondaryId="integrity-helper",SecondaryLabel="G-Report"}
  };}}
  public virtual string AppFolder(AppChoice app){return Path.Combine(Program.Root,"Apps",app.Folder);}
  public virtual CompanionChoice[] ExtraCompanions {get{return new CompanionChoice[0];}}
  public virtual LauncherAction[] ExtraActions {get{return new LauncherAction[0];}}
  public virtual LauncherAction[] Installers {get{return new[]{new LauncherAction{Id="install",Label=Name}};}}
  public virtual Target ResolveExtra(string id){return null;}
 }
 static partial class Program {
  public const string Version="2.2.0";
  public static string Root,Suite="professional";
  public static LauncherProfile Profile=new LauncherProfile();
  static partial void SelectProfile(ref LauncherProfile profile);
  public static bool Personal {get{return Suite=="personal";}}
  public static string SuiteName {get{return Profile.Name;}}
  public static string LauncherName {get{return SuiteName+".exe";}}
  public static AppChoice[] Apps {get{return Profile.Apps;}}
  public static CompanionChoice[] Companions {get{return Apps.Where(a=>a.SecondaryId!=null).Select(a=>new CompanionChoice{id=a.SecondaryId,label=a.SecondaryLabel,parent=a.Id,description=a.Id=="whiz"?"Organize your Rutgers Canvas courses.":a.Id=="scope"?"Capture Gradescope rubrics for your grading workspace.":"Prepare Rutgers integrity forms from an approved case.",icon=a.Id=="whiz"?"g-view":a.Id=="scope"?"g-rater":"g-report"}).Concat(Profile.ExtraCompanions).ToArray();}}
  public static LauncherAction[] Actions {get{return new[]{new LauncherAction{Id="extensions",Label="Chrome Extensions",Icon="chrome-extensions"}}.Concat(Profile.ExtraActions).ToArray();}}
  static readonly JavaScriptSerializer Json=new JavaScriptSerializer();
  public static void LoadSuite(){
   Suite="professional";
   foreach(string filename in new[]{"installation.json","root.json"}){
    string path=Path.Combine(Root,".gworks",filename);if(!File.Exists(path))continue;
    var record=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path));object suite;
    if(record.TryGetValue("suite",out suite)){Suite=Convert.ToString(suite).ToLowerInvariant();break;}
   }
   if(Suite!="professional"&&Suite!="personal")throw new Exception("Unknown installation profile.");
   Profile=new LauncherProfile();SelectProfile(ref Profile);
  }
  public static string AppFolder(AppChoice app){return Profile.AppFolder(app);}
  public static string Quote(string value){return "\""+value.Replace("\"","\\\"")+"\"";}
  public static Target Resolve(string id){
   if(id=="settings"||id=="ai-settings"){
    foreach(var installedApp in Apps){
     string settingsRoot=AppFolder(installedApp),python=Path.Combine(settingsRoot,"Dependencies","python","pythonw.exe"),script=Path.Combine(settingsRoot,"Dependencies","TeachingApp","settings_center.py");
     if(File.Exists(python)&&File.Exists(script))return new Target{File=python,Arguments="-I -B "+Quote(script)+" --root "+Quote(Directory.GetParent(Directory.GetParent(settingsRoot).FullName).FullName)+" --app "+installedApp.Id+(id=="ai-settings"?" --page ai":""),Directory=settingsRoot};
    }
    throw new Exception("Shared Settings is unavailable. Use Install / update to repair the desktop runtime.");
   }
   if(id=="folder")return new Target{File=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"explorer.exe"),Arguments=Quote(Root),Directory=Root,Shell=true};
   if(id=="install"){
    string setup=Path.Combine(Root,"Install "+SuiteName+".exe");if(!File.Exists(setup))throw new Exception(SuiteName+" Setup is missing from this folder.");
    return new Target{File=setup,Arguments="",Directory=Root,Shell=true};
   }
   Target extra=Profile.ResolveExtra(id);if(extra!=null)return extra;
   if(id=="vault"||id=="keeper")id="spot";
   var choice=Apps.FirstOrDefault(a=>a.Id==id||a.SecondaryId==id);
   if(choice==null)throw new Exception("Unknown workspace for "+SuiteName+".");
   string folder=AppFolder(choice),app=choice.Name;
   if(id=="rubric-lens"||id=="integrity-helper"||id=="course-organizer"){
    string python=Path.Combine(folder,"Dependencies","python","pythonw.exe"),script=Path.Combine(folder,"App","extension_setup.py");
    if(!File.Exists(script)||!File.Exists(python))throw new Exception("Install the parent app to add its Chrome extension.");
    return new Target{File=python,Arguments="-I -B "+Quote(script)+" --extension "+id,Directory=folder};
   }
   if(id=="scope"){
    string python=Path.Combine(folder,"Dependencies","python","pythonw.exe"),script=Path.Combine(folder,"App","Desktop","desktop.py");
    if(!File.Exists(python)||!File.Exists(script))throw new Exception("G-Scope desktop files are missing. Open Install / update to repair it.");
    return new Target{File=python,Arguments="-I -B "+Quote(script),Directory=folder};
   }
   string launch=Path.Combine(folder,"App","Launch.ps1");if(!File.Exists(launch))throw new Exception(app+" is not installed. Open Install / update to add it.");
   return new Target{File=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell","v1.0","powershell.exe"),Arguments="-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "+Quote(launch)+" -Desktop",Directory=folder};
  }
  public static bool NeedsAiReadiness(){return Apps.Any(a=>File.Exists(Path.Combine(AppFolder(a),"App","local_ai_startup.py")));}
  public static bool Available(string id){try{if(id=="extensions")return Companions.Length>0;var target=Resolve(id);return File.Exists(target.File)&&Directory.Exists(target.Directory);}catch{return false;}}
  public static string UnavailableReason(string id){try{Resolve(id);return "Required program files are missing.";}catch(Exception error){return error.Message;}}
  public static void Open(string id){var target=Resolve(id);Process.Start(new ProcessStartInfo(target.File,target.Arguments){WorkingDirectory=target.Directory,UseShellExecute=target.Shell,CreateNoWindow=!target.Shell});}
  static string FindRoot(){var directory=new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);for(int i=0;i<5&&directory!=null;i++,directory=directory.Parent)if(Directory.Exists(Path.Combine(directory.FullName,"Apps")))return directory.FullName;throw new Exception("Keep the launcher inside its suite folder.");}
  static int ForwardEntry(string[] args,bool check){
   var installed=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(Root,".gworks","installation.json")));
   string target=Path.GetFullPath(Path.Combine(Root,Convert.ToString(installed["launcher"]))),shared=Path.Combine(Root,"Shared","Launcher")+Path.DirectorySeparatorChar;
   if(!target.StartsWith(shared,StringComparison.OrdinalIgnoreCase)||string.Equals(target,Application.ExecutablePath,StringComparison.OrdinalIgnoreCase)||!File.Exists(target))throw new Exception("The current launcher is unavailable. Open Install "+SuiteName+".exe to repair it.");
   var start=new ProcessStartInfo(target,string.Join(" ",args.Select(Quote))){WorkingDirectory=Root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=check,RedirectStandardError=check};
   using(var process=Process.Start(start)){if(!check)return 0;Console.Write(process.StandardOutput.ReadToEnd());Console.Error.Write(process.StandardError.ReadToEnd());process.WaitForExit();return process.ExitCode;}
  }
  [STAThread]static int Main(string[] args){bool check=args.Any(a=>a=="--self-test"||a=="--describe"||a=="--describe-ui"||a=="--render-preview"||a=="--check-paint");try{
   int index=Array.IndexOf(args,"--root");Root=index>=0&&index+1<args.Length?Path.GetFullPath(args[index+1]):FindRoot();LoadSuite();
   if(string.Equals(Application.ExecutablePath,Path.Combine(Root,"Shared","Launcher",LauncherName),StringComparison.OrdinalIgnoreCase))return ForwardEntry(args,check);
   if(args.Contains("--self-test")){
    var result=new Dictionary<string,object>();foreach(string id in Apps.SelectMany(a=>a.SecondaryId==null?new[]{a.Id}:new[]{a.Id,a.SecondaryId}).Concat(Companions.Select(c=>c.id)).Concat(Profile.Installers.Select(i=>i.Id)).Concat(Actions.Select(a=>a.Id).Concat(new[]{"install","folder","settings"})))result[id]=new{available=Available(id)};
    result["suite"]=Suite;result["name"]=SuiteName;result["version"]=Version;result["nativeUIOpened"]=false;Console.WriteLine(Json.Serialize(result));return 0;
   }
   if(args.Contains("--describe-ui")){Console.WriteLine(Json.Serialize(new{version=Version,suite=Suite,name=SuiteName,width=HubArt.Width,height=HubArt.Height,apps=Apps,extensions=Companions,actions=Actions,installers=Profile.Installers,nativeUIOpened=false}));return 0;}
   if(args.Contains("--check-paint")){Console.WriteLine(Json.Serialize(HubArt.CheckPaint()));return 0;}
   index=Array.IndexOf(args,"--render-preview");if(index>=0){int scale=args.Contains("--2x")?2:1;int state=Array.IndexOf(args,"--state");HubArt.Preview(args[index+1],scale,state>=0?args[state+1]:"normal");return 0;}
   index=Array.IndexOf(args,"--describe");if(index>=0){Console.WriteLine(Json.Serialize(Resolve(args[index+1])));return 0;}
   index=Array.IndexOf(args,"--launch");if(index>=0){Open(args[index+1]);return 0;}
   string key;using(var sha=SHA256.Create())key=BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(Root.ToUpperInvariant()))).Replace("-","").Substring(0,20);
   bool created;using(var mutex=new Mutex(true,"Local\\GWorksHub-"+key,out created)){
    string wakeName="Local\\GWorksHubWake-"+key;
    using(var wake=new EventWaitHandle(false,EventResetMode.AutoReset,wakeName)){
     if(!created){wake.Set();return 0;}
     Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
     using(var window=new Hub()){
      var listener=new Thread(()=>{while(wake.WaitOne()){try{if(window.IsDisposed)return;if(window.IsHandleCreated)window.BeginInvoke((Action)(()=>{window.Show();if(window.WindowState==FormWindowState.Minimized)window.WindowState=FormWindowState.Normal;window.Activate();window.BringToFront();}));}catch(ObjectDisposedException){return;}catch(InvalidOperationException){return;}}});listener.IsBackground=true;
      window.Shown+=(sender,eventArgs)=>listener.Start();
      Application.Run(window);
     }
    }
   }return 0;
  }catch(Exception error){if(check)Console.Error.WriteLine(error.Message);else MessageBox.Show(error.Message,SuiteName,MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}}
 }
 class RaisedButton:Button {
  public AppChoice App;public string Glyph,Label,Detail;public Color Accent;public RectangleF SceneBounds;public RaisedButton Underlay;bool hover,pressed;
  public RaisedButton(){SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer|ControlStyles.ResizeRedraw|ControlStyles.Opaque,true);FlatStyle=FlatStyle.Flat;FlatAppearance.BorderSize=0;UseVisualStyleBackColor=false;BackColor=HubArt.Canvas;Cursor=Cursors.Hand;}
  protected override void OnMouseEnter(EventArgs e){hover=true;Invalidate();base.OnMouseEnter(e);}
  protected override void OnMouseLeave(EventArgs e){hover=pressed=false;Invalidate();base.OnMouseLeave(e);}
  protected override void OnMouseDown(MouseEventArgs e){pressed=e.Button==MouseButtons.Left;Invalidate();base.OnMouseDown(e);}
  protected override void OnMouseUp(MouseEventArgs e){pressed=false;Invalidate();base.OnMouseUp(e);}
  protected override void OnKeyDown(KeyEventArgs e){if(e.KeyCode==Keys.Space){pressed=true;Invalidate();}base.OnKeyDown(e);}
  protected override void OnKeyUp(KeyEventArgs e){pressed=false;Invalidate();base.OnKeyUp(e);}
  protected override void OnGotFocus(EventArgs e){Invalidate();base.OnGotFocus(e);}
  protected override void OnLostFocus(EventArgs e){pressed=false;Invalidate();base.OnLostFocus(e);}
  protected override void OnPaintBackground(PaintEventArgs e){} // PaintButton owns the full opaque buffer.
  protected override void OnPaint(PaintEventArgs e){var state=e.Graphics.Save();e.Graphics.ScaleTransform(ClientSize.Width/SceneBounds.Width,ClientSize.Height/SceneBounds.Height);e.Graphics.TranslateTransform(-SceneBounds.X,-SceneBounds.Y);
   HubArt.PaintButton(e.Graphics,SceneBounds,App,Label,Glyph,Accent,hover,pressed,Enabled,Focused&&ShowFocusCues,Underlay==null?null:Underlay.App,Underlay!=null&&Underlay.hover,Underlay!=null&&Underlay.pressed,Underlay==null||Underlay.Enabled,Underlay!=null&&Underlay.Focused&&Underlay.ShowFocusCues,Detail);
   e.Graphics.Restore(state);
  }
 }
 class Hub:Form {
  readonly Label status=new Label();readonly ToolTip tips=new ToolTip();
  readonly System.Windows.Forms.Timer statusTimer=new System.Windows.Forms.Timer{Interval=4000};
  readonly LinkLabel aiStatus=new LinkLabel();readonly RaisedButton installButton;bool checkingAi,canStartAi,aiNeedsSettings,checkingUpdates;
  public Hub(){statusTimer.Tick+=(sender,args)=>{statusTimer.Stop();status.Text="";};Disposed+=(sender,args)=>statusTimer.Dispose();Text=Program.SuiteName;ClientSize=new Size(HubArt.Width,HubArt.Height);FormBorderStyle=FormBorderStyle.FixedSingle;MaximizeBox=false;StartPosition=FormStartPosition.CenterScreen;AutoScaleDimensions=new SizeF(96,96);AutoScaleMode=AutoScaleMode.Dpi;BackColor=HubArt.Canvas;DoubleBuffered=true;Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
   for(int i=0;i<Program.Apps.Length;i++){
    AppChoice app=Program.Apps[i];RectangleF box=HubArt.TileBounds(i);var tile=new RaisedButton{App=app,SceneBounds=box,Bounds=Rectangle.Round(box),AccessibleName="Open "+app.Name,AccessibleDescription=app.Description,Enabled=Program.Available(app.Id),TabIndex=i*4};tile.Click+=(s,e)=>Run(app.Id);Controls.Add(tile);
   }
   for(int i=0;i<Program.Actions.Length;i++){var action=Program.Actions[i];var button=Utility(action.Label,action.Icon,HubArt.Ink,HubArt.ActionBounds(i),20+i,action.Id);button.Enabled=Program.Available(action.Id);if(!button.Enabled){button.Detail=action.UnavailableLabel;button.AccessibleDescription=Program.UnavailableReason(action.Id);tips.SetToolTip(button,button.AccessibleDescription);}Controls.Add(button);}
   installButton=Utility("Install / update","install",HubArt.Ink,HubArt.InstallBounds,12,"install");Controls.Add(installButton);
   Controls.Add(Utility("Open "+Program.SuiteName+" folder","folder",HubArt.Ink,HubArt.FolderBounds,13,"folder"));
   Controls.Add(Utility("Settings","settings",HubArt.Ink,HubArt.SettingsBounds,14,"settings"));
   bool usesAi=Program.NeedsAiReadiness();
   aiStatus.SetBounds(26,HubArt.StatusY,(HubArt.Width-68)/2,23);aiStatus.TabIndex=15;aiStatus.LinkColor=HubArt.ColorOf("#176b70");aiStatus.ActiveLinkColor=Color.White;aiStatus.Font=new Font("Segoe UI",8.5f);aiStatus.BackColor=Color.Transparent;aiStatus.AutoEllipsis=true;aiStatus.Visible=usesAi;aiStatus.Text=usesAi?"Checking local LLM...":"";aiStatus.AccessibleName="Local LLM readiness";aiStatus.LinkClicked+=(s,e)=>{if(aiNeedsSettings)Run("ai-settings");else CheckAi(canStartAi);};if(usesAi)Controls.Add(aiStatus);
   if(usesAi)Shown+=(s,e)=>CheckAi(true);
   status.SetBounds(26,HubArt.StatusY+26,HubArt.Width-52,22);status.ForeColor=HubArt.ColorOf("#4f6069");status.BackColor=Color.Transparent;status.AutoEllipsis=true;status.Font=new Font("Segoe UI",9);Controls.Add(status);
   Shown+=(s,e)=>CheckUpdates(false);
  }
  RaisedButton Utility(string label,string glyph,Color accent,RectangleF box,int order,string id){var button=new RaisedButton{Label=label,Glyph=glyph,Accent=accent,SceneBounds=box,Bounds=Rectangle.Round(box),AccessibleName=label,TabIndex=order};button.Click+=(s,e)=>Run(id);return button;}
  protected override void OnPaint(PaintEventArgs e){var state=e.Graphics.Save();e.Graphics.ScaleTransform(ClientSize.Width/(float)HubArt.Width,ClientSize.Height/(float)HubArt.Height);HubArt.Background(e.Graphics);HubArt.Header(e.Graphics);e.Graphics.Restore(state);base.OnPaint(e);}
  void SetStatus(LinkLabel label,string message,bool warning){
   string text=(warning?"\u26a0 ":"")+message;Color color=warning?HubArt.ColorOf("#b31d2c"):HubArt.ColorOf("#176b70");
   label.Text=text;label.LinkColor=color;label.ForeColor=color;label.ActiveLinkColor=color;label.VisitedLinkColor=color;label.AccessibleDescription=text;tips.SetToolTip(label,text);
  }
  internal void SetUpdateAvailability(string message,bool available){
   installButton.Detail=available?"Update available":null;
   installButton.AccessibleDescription=available?message:"";
   tips.SetToolTip(installButton,available?message:"");installButton.Invalidate();
  }
  void CheckUpdates(bool force){
   if(checkingUpdates)return;checkingUpdates=true;SetUpdateAvailability("",false);
   ReleaseUpdates.CheckAsync(this,Program.Root,Program.Version,
    notice=>{},null,force,
    (message,available)=>{checkingUpdates=false;SetUpdateAvailability(message,available);});
  }
  void CheckAi(bool start){
   if(checkingAi)return;checkingAi=true;aiStatus.Enabled=false;SetStatus(aiStatus,"Checking local LLM...",false);
   new Thread(()=>{
    string message="Local LLM check unavailable - Open AI settings.";bool canStart=false,warning=true;
    try{
     string spot=Program.Apps.Select(Program.AppFolder).FirstOrDefault(p=>File.Exists(Path.Combine(p,"App","local_ai_startup.py")));if(spot==null)throw new Exception("Local AI helper is unavailable.");
     string python=Path.Combine(spot,"Dependencies","python","python.exe"),helper=Path.Combine(spot,"App","local_ai_startup.py");
     var info=new ProcessStartInfo(python,"-I -B "+Program.Quote(helper)+(start?" --start":" --check")){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=spot};
     using(var process=Process.Start(info)){
      if(!process.WaitForExit(15000)){process.Kill();throw new Exception("Readiness check timed out.");}
      var data=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(process.StandardOutput.ReadToEnd());
      string state=Convert.ToString(data["state"]);warning=state!="ready"&&state!="available";canStart=data.ContainsKey("canStart")&&Convert.ToBoolean(data["canStart"]);
      string engine=data.ContainsKey("provider")&&Convert.ToString(data["provider"])=="ollama"?"Ollama LLM":"Local LLM";
      message=state=="ready"?engine+" loaded - Click to recheck.":state=="available"?engine+" available - Loads when needed.":state=="engine_offline"?(canStart?"Ollama stopped - Click to start.":"Local LLM offline - Check engine settings."):state=="starting"?"Ollama is starting - Click to recheck.":Convert.ToString(data["message"]);
     }
    }catch{}
    try{if(!IsDisposed)BeginInvoke(new Action(()=>{if(IsDisposed)return;checkingAi=false;canStartAi=canStart;aiNeedsSettings=warning&&!canStart;SetStatus(aiStatus,message,warning);aiStatus.Enabled=true;}));}catch{}
   }){IsBackground=true}.Start();
  }
  void Run(string id){statusTimer.Stop();try{if(id=="install"&&Program.Profile.Installers.Length>1){var menu=new ContextMenuStrip();foreach(var entry in Program.Profile.Installers){var choice=entry;var item=menu.Items.Add(choice.Label);item.Enabled=Program.Available(choice.Id);item.Click+=(s,e)=>{try{Program.Open(choice.Id);}catch(Exception error){status.Text=error.Message;}};}menu.Closed+=(s,e)=>menu.Dispose();menu.Show(installButton,new Point(0,installButton.Height));return;}if(id=="extensions"){using(var window=new ExtensionMenu())window.ShowDialog(this);return;}Program.Open(id);var app=Program.Apps.FirstOrDefault(a=>a.Id==id);status.Text=app==null?"":"Opening "+app.Name+"...";if(status.Text.Length>0)statusTimer.Start();}catch(Exception error){status.Text=error.Message;}}
 }
 class ExtensionMenu:Form {
  public ExtensionMenu(){Text="Chrome Extensions";ClientSize=new Size(570,Math.Max(160,Program.Companions.Length*100+32));FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;MinimizeBox=false;StartPosition=FormStartPosition.CenterParent;Font=new Font("Segoe UI",9);BackColor=Color.FromArgb(255,253,248);AutoScaleMode=AutoScaleMode.Dpi;
   int y=16;foreach(var companion in Program.Companions){var entry=companion;
    var mark=new PictureBox{Image=HubArt.ImageFor(entry.icon),Bounds=new Rectangle(18,y+10,42,42),SizeMode=PictureBoxSizeMode.Zoom};Controls.Add(mark);
    Controls.Add(new Label{Text=entry.label,Bounds=new Rectangle(76,y+2,310,24),Font=new Font("Segoe UI",11,FontStyle.Bold)});
    Controls.Add(new Label{Text=entry.description,Bounds=new Rectangle(76,y+29,310,48)});
    var install=new Button{Text="Install / open",Bounds=new Rectangle(414,y+15,132,34),Enabled=Program.Available(entry.id)};install.Click+=(s,e)=>{try{Program.Open(entry.id);}catch(Exception error){MessageBox.Show(this,error.Message,entry.label);}};Controls.Add(install);y+=100;
   }
  }
 }

}
