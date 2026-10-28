using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using System.Drawing;

namespace GWorks {
  static class Program {
    public static string Bootstrap;
    public static JavaScriptSerializer Json = new JavaScriptSerializer();
#if PERSONAL_SUITE
    public const string DefaultSuite="personal";
#else
    public const string DefaultSuite="professional";
#endif
    public static string SuiteName(string suite) {return suite=="personal"?"Application":"G-Works";}
    public static bool SharedAiManagedExternally(string root) {
      try {string full=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);string parent=Path.GetDirectoryName(full);
        if(!String.Equals(Path.GetFileName(full),"Application",StringComparison.OrdinalIgnoreCase)||String.IsNullOrEmpty(parent))return false;
        string owner=Path.Combine(parent,"G-Works");return File.Exists(Path.Combine(owner,".gworks","root.json"))&&Directory.Exists(Path.Combine(owner,"Apps"))&&Directory.Exists(Path.Combine(owner,"Shared"));
      }catch{return false;}
    }
    public static string ReadSuite(string root) {
      string found=null;
      foreach(string name in new[]{"root.json","installation.json"}){
        string path=Path.Combine(root,".gworks",name);if(!File.Exists(path))continue;
        var record=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path));if(!record.ContainsKey("suite"))continue;
        string value=Convert.ToString(record["suite"]);if(value!="professional"&&value!="personal")throw new Exception("Unknown installation suite.");
        if(found!=null&&found!=value)throw new Exception("Installation suite records disagree.");found=value;
      }
      return found??DefaultSuite;
    }
    [STAThread] static int Main(string[] args) {
      try {
        Bootstrap = Path.Combine(Path.GetTempPath(), "GWorksSetup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Bootstrap);
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("bootstrap.zip")) {
          if (resource == null) throw new Exception("The installer payload is missing.");
          using (ZipArchive zip = new ZipArchive(resource, ZipArchiveMode.Read)) {
            foreach (ZipArchiveEntry entry in zip.Entries) {
              string full = Path.GetFullPath(Path.Combine(Bootstrap, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
              if (!full.StartsWith(Bootstrap + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) || entry.FullName.Contains(":") || (entry.ExternalAttributes >> 16 & 0xF000) == 0xA000) throw new Exception("Unsafe bootstrap path.");
              if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(full); continue; }
              Directory.CreateDirectory(Path.GetDirectoryName(full));
              using (Stream input = entry.Open()) using (FileStream output = File.Create(full)) input.CopyTo(output);
            }
          }
        }
        if (args.Contains("--self-test")) {
          // Validate the signed public dependency graph without activating any private app.
          Dictionary<string, object> options = new Dictionary<string, object>(); options["apps"] = new string[] {DefaultSuite=="personal"?"willikers":"scope"};
          ProcessStartInfo start = Engine("--plan");
          using (Process process = Process.Start(start)) {
            process.StandardInput.Write(Json.Serialize(options)); process.StandardInput.Close();
            string output = process.StandardOutput.ReadToEnd(); string errors = process.StandardError.ReadToEnd(); process.WaitForExit();
            Console.WriteLine(output); if (process.ExitCode != 0) throw new Exception(errors + output);
          }
          return 0;
        }
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        var wizard=new Wizard();
        if(DefaultSuite=="professional")wizard.BeginInstallerCheck();
        Application.Run(wizard); return 0;
      } catch (Exception error) {
        if (args.Contains("--self-test")) Console.Error.WriteLine(error.Message);
        else MessageBox.Show(error.Message, SuiteName(DefaultSuite)+" Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
        return 1;
      } finally { try { if (Bootstrap != null) Directory.Delete(Bootstrap, true); } catch {} }
    }
    public static string Quote(string value) { return "\"" + value.Replace("\"", "\\\"") + "\""; }
    public static ProcessStartInfo Engine(string extra) {
      string scripts = Path.Combine(Bootstrap, "Installer");
      string executableFolder=Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
      string offline = Path.Combine(executableFolder, "Packages");
      if(!Directory.Exists(offline)&&File.Exists(Path.Combine(executableFolder,".gworks","root.json"))){
        var rootRecord=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(executableFolder,".gworks","root.json")));
        object registered;
        if(rootRecord.TryGetValue("package_root",out registered)&&registered is string&&Path.IsPathRooted((string)registered))offline=Path.GetFullPath((string)registered);
      }
      if(!Directory.Exists(offline)&&!File.Exists(Path.Combine(executableFolder,".gworks","root.json")))offline=executableFolder;
      ProcessStartInfo start = new ProcessStartInfo(Path.Combine(Bootstrap, "Python", "python.exe"));
      start.Arguments = "-I -B " + Quote(Path.Combine(scripts,"engine.py")) + " --catalogue " + Quote(Path.Combine(scripts,"catalogue.json")) + " --signature " + Quote(Path.Combine(scripts,"catalogue.sig")) + " --key " + Quote(Path.Combine(scripts,"public-key.json")) + " --offline " + Quote(offline) + " " + extra;
      start.UseShellExecute = false; start.CreateNoWindow = true; start.RedirectStandardInput = true; start.RedirectStandardOutput = true; start.RedirectStandardError = true; start.StandardOutputEncoding = Encoding.UTF8; start.StandardErrorEncoding = Encoding.UTF8;
      return start;
    }
  }
  class Wizard : Form {
    readonly List<string> ids=new List<string>();
    readonly Dictionary<string,string> names=new Dictionary<string,string>();
    readonly CheckedListBox apps = new CheckedListBox(), courses=new CheckedListBox();
    readonly List<string> courseIds=new List<string>();
    readonly TextBox folder=new TextBox(), texBin=new TextBox(), model=new TextBox(), revision=new TextBox(), localUrl=new TextBox();
    readonly TextBox customCourse=new TextBox(),customName=new TextBox(),instructorName=new TextBox(),instructorTitle=new TextBox(),instructorEmail=new TextBox(),instructorPhone=new TextBox(),instructorOffice=new TextBox(),instructorWebsite=new TextBox();
    readonly ComboBox texChoice=new ComboBox(), aiChoice=new ComboBox();
    readonly CheckBox verifyTex=new CheckBox(), repairTex=new CheckBox(), dependencyOnly=new CheckBox(), chatgpt=new CheckBox(), latest=new CheckBox(), launch=new CheckBox(), shortcuts=new CheckBox(), keepQuestions=new CheckBox();
    readonly Button next=new Button(), back=new Button();
    readonly Panel page=new Panel();
    readonly Label status=new Label();
    readonly ProgressBar progress=new ProgressBar();
    readonly bool ownerMode;
    readonly string suite,suiteName;
    int step=0; bool installing=false,complete=false,loadingDetection=false,hasSavedAI=false,sharedAiExternallyManaged=false,checkingInstaller=false; string installedRoot="";
    public void BeginInstallerCheck(){checkingInstaller=true;Shown+=(s,e)=>System.Threading.ThreadPool.QueueUserWorkItem(delegate{UpdateNotice notice=null;try{var catalog=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(Program.Bootstrap,"Installer/catalogue.json")));notice=ReleaseUpdates.FetchNotice(Convert.ToString(catalog["release"]),File.ReadAllText(Path.Combine(Program.Bootstrap,"Installer/public-key.json")));}catch{}try{BeginInvoke(new Action(delegate{checkingInstaller=false;if(notice!=null){try{ReleaseUpdates.PromptDownload(this,notice);}finally{Close();}}}));}catch{}});}
    public Wizard() {
      string localRoot=Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);bool localInstall=File.Exists(Path.Combine(localRoot,".gworks","root.json"));
      suite=Program.ReadSuite(localRoot);suiteName=Program.SuiteName(suite);
      string release=Convert.ToString(Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(Program.Bootstrap,"Installer/catalogue.json")))["release"]);
      Text=suiteName+" Setup — "+new SemVersion(release).Display; Width=730; Height=815; MinimumSize=new Size(700,795); StartPosition=FormStartPosition.CenterScreen; Font=new Font("Segoe UI",10); BackColor=Color.FromArgb(246,249,251);
      Label title=new Label(); title.Text=suiteName+" · "+new SemVersion(release).Display; title.Font=new Font("Segoe UI",24,FontStyle.Bold); title.SetBounds(30,20,650,45); Controls.Add(title);
      Label subtitle=new Label(); subtitle.Text="Install, update or change your "+suiteName+" setup"; subtitle.ForeColor=Color.FromArgb(75,96,110); subtitle.SetBounds(33,68,650,25); Controls.Add(subtitle);
      page.SetBounds(32,110,650,565); page.Anchor=AnchorStyles.Top|AnchorStyles.Bottom|AnchorStyles.Left|AnchorStyles.Right; Controls.Add(page);
      back.Text="Back"; back.SetBounds(455,715,100,35); back.Anchor=AnchorStyles.Bottom|AnchorStyles.Right; back.Click+=(s,e)=>{step=(suite=="personal"&&step==2)?0:step-1;Draw();};Controls.Add(back);
      next.Text="Next"; next.SetBounds(565,715,115,35); next.Anchor=AnchorStyles.Bottom|AnchorStyles.Right; next.BackColor=Color.FromArgb(35,108,77);next.ForeColor=Color.White;next.FlatStyle=FlatStyle.Flat;next.Click+=Next;Controls.Add(next);
      apps.CheckOnClick=true; apps.BorderStyle=BorderStyle.FixedSingle;
      Dictionary<string,object> catalog=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(Program.Bootstrap,"Installer","catalogue.json")));
      ownerMode=Convert.ToString(catalog["channel"])=="owner";
      foreach(object value in (System.Collections.IEnumerable)catalog["applications"]) {
        Dictionary<string,object> app=(Dictionary<string,object>)value;string id=Convert.ToString(app["id"]),name=Convert.ToString(app["name"]);
        string appSuite=app.ContainsKey("suite")?Convert.ToString(app["suite"]):(id=="willikers"||id=="mods"?"personal":"professional");if(appSuite!=suite)continue;
        if(id=="vault")name="G-Vault";
        ids.Add(id);names[id]=name;bool isPublic=suite=="professional";
        apps.Items.Add(name+" — "+Convert.ToString(app["description"])+(isPublic?" · public":" · private repository"),localInstall?Directory.Exists(Path.Combine(localRoot,"Apps",name)):id==(suite=="personal"?"willikers":"whiz"));
      }
      courses.CheckOnClick=true;courses.BorderStyle=BorderStyle.FixedSingle;
      if(suite=="professional"&&catalog.ContainsKey("courses"))foreach(object item in (System.Collections.IEnumerable)catalog["courses"]){var course=(Dictionary<string,object>)item;string id=Convert.ToString(course["id"]);if(id=="136")continue;courseIds.Add(id);courses.Items.Add(Convert.ToString(course["name"]),localInstall?File.Exists(Path.Combine(localRoot,"Shared","Courses",id,"manifest.json")):false);}
      apps.ItemCheck+=(s,e)=>{
        int whiz=ids.IndexOf("whiz"),scope=ids.IndexOf("scope");
        if(ids[e.Index]=="scope"&&e.NewValue==CheckState.Checked&&whiz>=0)apps.SetItemChecked(whiz,true);
        if(ids[e.Index]=="whiz"&&e.NewValue==CheckState.Unchecked&&scope>=0&&apps.GetItemChecked(scope))e.NewValue=CheckState.Checked;
        if(IsHandleCreated)BeginInvoke((Action)(()=>{courses.Enabled=Selected().Contains("whiz");keepQuestions.Enabled=suite=="professional"&&Selected().Contains("whiz")&&!dependencyOnly.Checked;}));
      };
      if(ids.Contains("scope")&&apps.GetItemChecked(ids.IndexOf("scope")))apps.SetItemChecked(ids.IndexOf("whiz"),true);
      folder.Text=localInstall?localRoot:Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),suiteName);
      sharedAiExternallyManaged=Program.SharedAiManagedExternally(folder.Text);
      texChoice.DropDownStyle=ComboBoxStyle.DropDownList;texChoice.Items.AddRange(new object[]{"Use existing TeX Live / MiKTeX","Install TeX Live Full","Install TeX Live Essentials"});texChoice.SelectedIndex=0;
      aiChoice.DropDownStyle=ComboBoxStyle.DropDownList;aiChoice.Items.AddRange(new object[]{"Keep current local AI (existing installation)","Use / install Ollama","Use another local AI server"});aiChoice.SelectedIndex=localInstall||sharedAiExternallyManaged?0:1;
      localUrl.Text="http://127.0.0.1:11434";
      aiChoice.SelectedIndexChanged+=(s,e)=>{if(!loadingDetection){localUrl.Text=aiChoice.SelectedIndex==2?"http://127.0.0.1:1234":"http://127.0.0.1:11434";revision.Clear();if(aiChoice.SelectedIndex==1)model.Text="qwen3-vl:4b";}UpdateAiFields();};
      verifyTex.Text="Check required TeX packages and compile a test PDF";verifyTex.Checked=true;
      repairTex.Text="Install missing TeX packages if required";verifyTex.CheckedChanged+=(s,e)=>repairTex.Enabled=verifyTex.Checked;
      chatgpt.Text="Open General AI settings after setup to connect ChatGPT (optional)";
      latest.Text="Check the public G-Works release channel";latest.Checked=suite=="professional"&&!localInstall;latest.Enabled=suite=="professional";
      keepQuestions.Text="Keep my question bank and saved handouts";keepQuestions.Checked=true;
      shortcuts.Text="Add "+suiteName+" to the Start menu";shortcuts.Checked=true;
      dependencyOnly.Text="Change dependencies only (keep app files)";dependencyOnly.Enabled=localInstall;
      dependencyOnly.CheckedChanged+=(s,e)=>keepQuestions.Enabled=Selected().Contains("whiz")&&!dependencyOnly.Checked;
      dependencyOnly.Checked=localInstall&&(!catalog.ContainsKey("suite_layout")||Convert.ToInt32(catalog["suite_layout"])!=1);
      folder.TextChanged+=(s,e)=>{dependencyOnly.Enabled=File.Exists(Path.Combine(folder.Text,".gworks","root.json"));if(!dependencyOnly.Enabled)dependencyOnly.Checked=false;sharedAiExternallyManaged=Program.SharedAiManagedExternally(folder.Text);if(sharedAiExternallyManaged)aiChoice.SelectedIndex=0;UpdateAiFields();};
      launch.Text="Open the selected apps when I click Finish";
      model.Text="qwen3-vl:4b";
      FormClosing+=(s,e)=>{if(installing){e.Cancel=true;status.Text="Setup is still running. Wait for it to finish before closing.";}};
      Load+=async(s,e)=>{string location=folder.Text;await System.Threading.Tasks.Task.Run(()=>Detect(location));};UpdateAiFields();Draw();
    }
    Label LabelAt(string text,int top,int height=25) { Label label=new Label();label.Text=text;label.SetBounds(0,top,640,height);page.Controls.Add(label);return label; }
    void Field(Control control,int top,int height=30) {control.SetBounds(0,top,640,height);page.Controls.Add(control);}
    void Draw() {
      page.Controls.Clear();back.Visible=step>0&&!complete;next.Enabled=true;
      if(step==0) {
        LabelAt("Choose the apps to install or update",0);Field(apps,27,108);
        LabelAt(suite=="personal"?"Your private applications.":"G-Scope requires G-Whiz. Choose course content:",143,50);if(suite=="professional"){Field(courses,171,70);LabelAt("Or start empty: course number / optional name",244);Field(customCourse,270);customCourse.Width=90;customCourse.MaxLength=3;customName.SetBounds(100,270,540,30);page.Controls.Add(customName);}courses.Enabled=Selected().Contains("whiz");
        LabelAt(suiteName+" installation folder",310);Field(folder,337);folder.Width=535;
        Button browse=new Button();browse.Text="Browse…";browse.SetBounds(545,336,95,32);browse.Click+=(s,e)=>{using(FolderBrowserDialog picker=new FolderBrowserDialog()){picker.Description="Choose the "+suiteName+" installation folder";if(picker.ShowDialog()==DialogResult.OK)folder.Text=picker.SelectedPath;}};page.Controls.Add(browse);
        LabelAt(suite=="personal"?"Download the complete private release with your GitHub account. ":"G-Whiz, G-Scope and G-Vault are public.",373,suite=="professional"?40:60);
        if(suite=="professional"){Field(latest,416);Field(shortcuts,446);Field(keepQuestions,476);Field(dependencyOnly,506);keepQuestions.Enabled=Selected().Contains("whiz")&&!dependencyOnly.Checked;}else{Field(latest,440);Field(shortcuts,470);Field(dependencyOnly,500);}
        next.Text="Next";
      } else if(step==1&&suite=="professional") {
        LabelAt("Your instructor details",0);LabelAt("Rutgers University · Department of Mathematics",30,40);
        LabelAt("Name",80);Field(instructorName,105);LabelAt("Title",145);Field(instructorTitle,170);LabelAt("Email",210);Field(instructorEmail,235);LabelAt("Phone",275);Field(instructorPhone,300);LabelAt("Office",340);Field(instructorOffice,365);LabelAt("Website",405);Field(instructorWebsite,430);
        LabelAt("Existing instructor details are kept when updating.",475,45);next.Text="Next";
      } else if(step==2) {
        if(Selected().All(id=>id=="mods"||id=="spot")){LabelAt("These apps use their own local settings. No TeX or AI setup is required.",0,60);next.Text="Apply / update";return;}
        LabelAt("TeX compiler",0);Field(texChoice,27);Field(texBin,66);texBin.Width=535;texBin.AccessibleName="Existing TeX bin folder";
        var browseTex=new Button{Text="Browse…"};browseTex.SetBounds(545,65,95,32);browseTex.Click+=(s,e)=>{using(var picker=new FolderBrowserDialog()){picker.Description="Choose the TeX Live or MiKTeX bin folder";if(picker.ShowDialog()==DialogResult.OK){texBin.Text=picker.SelectedPath;texChoice.SelectedIndex=0;}}};page.Controls.Add(browseTex);
        if(sharedAiExternallyManaged){
          LabelAt("Shared AI is managed in G-Works Settings or Install / update. This setup keeps that choice.",109,55);
          Field(verifyTex,177);Field(repairTex,210);
        }else{
          LabelAt("Local AI provider",109);Field(aiChoice,136);
          LabelAt("Local server address",177);Field(localUrl,202);
          LabelAt("Local model (image grading requires a vision model)",243);Field(model,269);
          LabelAt("Model revision / fingerprint (other local servers)",309);Field(revision,335);
          Field(verifyTex,378);Field(repairTex,411);Field(chatgpt,449,45);
        }
        next.Text="Apply / update";UpdateAiFields();
      } else {
        status.AutoSize=false;status.SetBounds(0,0,640,250);page.Controls.Add(status);
        progress.SetBounds(0,270,640,22);progress.Style=complete?ProgressBarStyle.Continuous:ProgressBarStyle.Marquee;page.Controls.Add(progress);
        if(complete){progress.Value=100;Field(launch,318);next.Text="Finish";}else{next.Text="Installing…";next.Enabled=false;back.Visible=false;}
      }
    }
    void UpdateAiFields(){aiChoice.Enabled=!sharedAiExternallyManaged;localUrl.Enabled=!sharedAiExternallyManaged&&aiChoice.SelectedIndex==2;revision.Enabled=!sharedAiExternallyManaged&&aiChoice.SelectedIndex==2;model.Enabled=!sharedAiExternallyManaged&&aiChoice.SelectedIndex!=0;}
    void Detect(string location) {
      try {
        ProcessStartInfo start=Program.Engine("");start.Arguments="-I -B "+Program.Quote(Path.Combine(Program.Bootstrap,"Installer","engine.py"))+" --detect";
        using(Process child=Process.Start(start)) {
          child.StandardInput.Write(Program.Json.Serialize(new{root=location}));child.StandardInput.Close();string raw=child.StandardOutput.ReadToEnd();child.WaitForExit(10000);
          Dictionary<string,object> found=Program.Json.Deserialize<Dictionary<string,object>>(raw);
          BeginInvoke((Action)(()=>{
            if(step!=0||folder.Text!=location)return;loadingDetection=true;texBin.Text=Convert.ToString(found["tex_bin"]);if(String.IsNullOrEmpty(texBin.Text))texChoice.SelectedIndex=1;
            System.Collections.IList local=found["local_ai"] as System.Collections.IList;
            var configured=found.ContainsKey("configured")?found["configured"] as Dictionary<string,object>:null;
            sharedAiExternallyManaged=Program.SharedAiManagedExternally(location);
            if(configured!=null&&configured.ContainsKey("local_ai")){
              var current=(Dictionary<string,object>)configured["local_ai"];hasSavedAI=true;aiChoice.SelectedIndex=0;model.Text=Convert.ToString(current["model"]);localUrl.Text=Convert.ToString(current["url"]);revision.Text=Convert.ToString(current["revision"]);
            }else if(local!=null&&local.Count>0){
              var first=(Dictionary<string,object>)local[0];aiChoice.SelectedIndex=Convert.ToString(first["provider"])=="ollama"?1:2;localUrl.Text=Convert.ToString(first["url"]);var models=first["models"] as System.Collections.IList;if(models!=null&&models.Count>0)model.Text=Convert.ToString(models[0]);
            }else aiChoice.SelectedIndex=1;
            if(sharedAiExternallyManaged)aiChoice.SelectedIndex=0;
            loadingDetection=false;UpdateAiFields();
          }));
        }
      } catch {} // Detection failure leaves explicit install choices available.
    }
    async void Next(object sender,EventArgs e) {
      if(checkingInstaller){MessageBox.Show(this,"Checking whether a newer installer is available. Please try again in a moment.",Text);return;}
      if(complete) { if(launch.Checked) foreach(string app in Selected()) OpenApp(installedRoot,app);Close();return; }
      if(step==0){
        if(apps.CheckedItems.Count==0){MessageBox.Show("Choose at least one app.",Text);return;}
        bool existing=Directory.Exists(Path.Combine(folder.Text,"Apps","G-Whiz","Data"));
        if(Selected().Contains("whiz")&&!dependencyOnly.Checked&&!existing&&!courses.CheckedIndices.Cast<int>().Any(i=>courseIds[i]!="discontinued")&&String.IsNullOrWhiteSpace(customCourse.Text)){MessageBox.Show("Choose a course pack or enter a course number for an empty workspace.",Text);return;}
        if(!String.IsNullOrWhiteSpace(customCourse.Text)&&(!System.Text.RegularExpressions.Regex.IsMatch(customCourse.Text.Trim(),"^[0-9]{3}$")||customCourse.Text.Trim()=="136")){MessageBox.Show("Enter an active three-digit Rutgers Math course number. Math 136 is discontinued.",Text);return;}
        step=suite=="professional"?1:2;Draw();return;
      }
      if(step==1){
        if(String.IsNullOrWhiteSpace(instructorName.Text)&&!Selected().Any(id=>Directory.Exists(Path.Combine(folder.Text,"Apps",names[id],"Data")))){MessageBox.Show("Enter your name before installing.",Text);return;}
        step=2;Draw();return;
      }
      if(step!=2)return;
      sharedAiExternallyManaged=Program.SharedAiManagedExternally(folder.Text);
      bool needsTools=Selected().Any(id=>id!="mods"&&id!="spot");
      if(needsTools&&!sharedAiExternallyManaged&&aiChoice.SelectedIndex==0&&!hasSavedAI){MessageBox.Show("Choose Ollama or another local AI server for this installation.",Text);return;}
      if(needsTools&&!sharedAiExternallyManaged&&String.IsNullOrWhiteSpace(model.Text)){MessageBox.Show("Choose a local model before installing.",Text);return;}
      Dictionary<string,object> options=new Dictionary<string,object>();options["root"]=folder.Text;options["apps"]=Selected();options["courses"]=courses.CheckedIndices.Cast<int>().Select(i=>courseIds[i]).ToArray();options["tex_choice"]=new string[]{"existing","full","essentials"}[texChoice.SelectedIndex];options["tex_bin"]=texBin.Text;options["ai_choice"]=new string[]{"keep","ollama","openai-local"}[aiChoice.SelectedIndex];options["local_ai_url"]=localUrl.Text;options["change_dependencies"]=true;options["verify_packages"]=verifyTex.Checked;options["repair_packages"]=verifyTex.Checked&&repairTex.Checked;options["model"]=model.Text;options["connect_chatgpt"]=chatgpt.Checked;options["check_updates"]=latest.Checked;
      options["suite"]=suite;
      if(!String.IsNullOrWhiteSpace(customCourse.Text))options["custom_course"]=new{code=customCourse.Text.Trim(),name=customName.Text.Trim()};
      if(!String.IsNullOrWhiteSpace(instructorName.Text))options["instructor_profile"]=new{name=instructorName.Text,title=instructorTitle.Text,email=instructorEmail.Text,phone=instructorPhone.Text,office=instructorOffice.Text,website=instructorWebsite.Text};
      if(sharedAiExternallyManaged){options["ai_choice"]="keep";options["connect_chatgpt"]=false;}
      options["model_revision"]=revision.Text;options["installer_exe"]=Assembly.GetExecutingAssembly().Location;
      options["dependencies_only"]=dependencyOnly.Checked;
      options["keep_custom_questions"]=!keepQuestions.Enabled||keepQuestions.Checked;
      if(keepQuestions.Enabled&&!keepQuestions.Checked&&(Directory.Exists(Path.Combine(folder.Text,"Apps","G-Whiz","Data","Question Bank"))||Directory.Exists(Path.Combine(folder.Text,"Apps","G-Whiz","mh-git","exercise-bank")))){
        if(MessageBox.Show("Start with a fresh question bank? The current bank and saved handouts will be kept in a local Question Bank Backups folder.",Text,MessageBoxButtons.OKCancel,MessageBoxIcon.Question)!=DialogResult.OK)return;
      }
      if(File.Exists(Path.Combine(folder.Text,".gworks","install.lock"))) {
        if(MessageBox.Show("Recover an interrupted setup before continuing? An installer that is still running will be left alone.",Text,MessageBoxButtons.OKCancel,MessageBoxIcon.Question)!=DialogResult.OK)return;
        options["repair"]=true;
      }
      step=3;installing=true;status.Text="Preparing verified packages…";Draw();
      try {
        int exit=await System.Threading.Tasks.Task.Run(()=>Run(options));
        installing=false;
        if(exit!=0){step=2;Draw();MessageBox.Show("Setup did not finish. "+status.Text+"\nYour existing saved work was retained.",Text,MessageBoxButtons.OK,MessageBoxIcon.Error);return;}
        complete=true;installedRoot=folder.Text;status.Text="Your selected "+suiteName+" setup is complete.\n\nYour saved data stays separate from application updates.";
        if(shortcuts.Checked){try{CreateShortcuts(installedRoot);}catch{status.Text+="\n\nStart menu shortcuts could not be created. Use the Open command in each installed app folder.";}}
        Draw();
      } catch(Exception error){installing=false;step=2;Draw();MessageBox.Show(error.Message,Text,MessageBoxButtons.OK,MessageBoxIcon.Error);}
      finally{}
    }
    string[] Selected(){return apps.CheckedIndices.Cast<int>().Select(i=>ids[i]).ToArray();}
    int Run(Dictionary<string,object> options) {
      using(Process child=new Process()) {
        child.StartInfo=Program.Engine("");child.OutputDataReceived+=(s,e)=>{if(e.Data==null)return;try{Dictionary<string,object> item=Program.Json.Deserialize<Dictionary<string,object>>(e.Data);string text=Convert.ToString(item["message"]);BeginInvoke((Action)(()=>status.Text=text));}catch{}};
        // Dependency programs can emit large diagnostics. Drain without retaining messages or credentials.
        child.ErrorDataReceived+=(s,e)=>{};
        child.Start();child.BeginOutputReadLine();child.BeginErrorReadLine();child.StandardInput.Write(Program.Json.Serialize(options));child.StandardInput.Close();child.WaitForExit();return child.ExitCode;
      }
    }
    void OpenApp(string root,string app) {
      string name=names[app];
      if(app=="mods"||app=="spot"){Process.Start(new ProcessStartInfo(Path.Combine(root,"Apps",name,"build",name+".exe")){UseShellExecute=false,WorkingDirectory=Path.Combine(root,"Apps",name)});return;}
      string script=Path.Combine(root,"Apps",name,"App","Launch.ps1");
      ProcessStartInfo start=new ProcessStartInfo("powershell.exe","-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "+Program.Quote(script)+" -Desktop");start.UseShellExecute=false;start.CreateNoWindow=true;Process.Start(start);
    }
    void CreateShortcuts(string root) {
      string launcher=Path.Combine(Path.GetFullPath(root),"Shared","Launcher",suiteName+".exe");
      if(!launcher.StartsWith(Path.GetFullPath(root)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||!File.Exists(launcher))throw new Exception(suiteName+" launcher is unavailable.");
      string menu=Environment.GetFolderPath(Environment.SpecialFolder.Programs);Directory.CreateDirectory(menu);
      object shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
      try{object link=shell.GetType().InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{Path.Combine(menu,suiteName+".lnk")});
        try{
          Action<string,object> set=(property,value)=>link.GetType().InvokeMember(property,BindingFlags.SetProperty,null,link,new object[]{value});
          set("TargetPath",launcher);set("Arguments","--root "+Program.Quote(root));set("WorkingDirectory",root);set("IconLocation",launcher+",0");
          link.GetType().InvokeMember("Save",BindingFlags.InvokeMethod,null,link,null);
        }finally{System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);}
      }finally{System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);}
    }
  }
}
