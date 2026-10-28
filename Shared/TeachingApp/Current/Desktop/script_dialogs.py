"""Owned, themed script dialogs. Message/input contents are never logged or saved."""
import logging
import appearance
log=logging.getLogger('local.desktop.dialogs')
CAPTURE_ALERT="Object.defineProperty(window,'__gworksBrowserAlert',{value:window.alert,configurable:true});"
RESTORE_ALERT="if(window.__gworksBrowserAlert)window.alert=window.__gworksBrowserAlert;"

def show(owner,brand,kind,message,default_text='',theme='daylight'):
    from System.Drawing import Color,Font,FontStyle,Size,Point
    from System.Windows.Forms import Form,FormBorderStyle,FormStartPosition,DialogResult,Label,TextBox,Button,FlatStyle,BorderStyle,ScrollBars,TextRenderer,TextFormatFlags,AutoScaleMode
    colors=appearance.palette(theme,brand['name']);rgb=lambda value:Color.FromArgb(int(value[1:3],16),int(value[3:5],16),int(value[5:7],16));dialog=Form();shade=Form()
    try:
        shade.FormBorderStyle=getattr(FormBorderStyle,'None');shade.StartPosition=FormStartPosition.Manual;shade.Bounds=owner.Bounds;shade.BackColor=Color.Black;shade.Opacity=.32;shade.ShowInTaskbar=False;shade.TopMost=owner.TopMost
        dialog.Text=brand['name'];dialog.FormBorderStyle=FormBorderStyle.FixedDialog;dialog.StartPosition=FormStartPosition.CenterParent;dialog.ShowInTaskbar=False;dialog.MaximizeBox=False;dialog.MinimizeBox=False;dialog.TopMost=owner.TopMost;dialog.AutoScaleMode=AutoScaleMode.Dpi
        dialog.Font=Font('Segoe UI',10);dialog.BackColor=rgb(colors['surface']);dialog.ForeColor=rgb(colors['ink']);dialog.ClientSize=Size(520,250)
        strip=Label();strip.BackColor=rgb(colors.get('accent',brand.get('accent','#7652a8')));strip.Location=Point(0,0);strip.Size=Size(520,5);dialog.Controls.Add(strip)
        heading=Label();heading.Text={'Prompt':'Enter a value','Confirm':'Confirm action','Beforeunload':'Leave this page?','Alert':'Notice'}.get(kind,'Notice');heading.Font=Font('Segoe UI',14,FontStyle.Bold);heading.Location=Point(23,23);heading.Size=Size(474,30);dialog.Controls.Add(heading)
        measured=TextRenderer.MeasureText(message,dialog.Font,Size(472,10000),TextFormatFlags.WordBreak);height=max(28,min(250,measured.Height+8))
        body=TextBox();body.Text=message;body.Multiline=True;body.ReadOnly=True;body.TabStop=False;body.BorderStyle=getattr(BorderStyle,'None');body.BackColor=dialog.BackColor;body.ForeColor=dialog.ForeColor;body.Location=Point(25,66);body.Size=Size(470,height);body.ScrollBars=ScrollBars.Vertical if measured.Height>height else getattr(ScrollBars,'None');body.AccessibleName='Message';dialog.Controls.Add(body)
        bottom=66+height+18;field=None
        if kind=='Prompt':
            field=TextBox();field.Text=default_text;field.Location=Point(25,bottom);field.Size=Size(470,30);field.AccessibleName=message;field.BackColor=rgb(colors['paper']);field.ForeColor=dialog.ForeColor;dialog.Controls.Add(field);bottom+=50
        okay=Button();okay.Text='OK';okay.Size=Size(92,34);okay.Location=Point(403,bottom);okay.DialogResult=DialogResult.OK;okay.FlatStyle=FlatStyle.Flat;okay.FlatAppearance.BorderSize=0;okay.BackColor=rgb(colors.get('accent',brand.get('accent','#7652a8')));okay.ForeColor=Color.White;dialog.Controls.Add(okay);dialog.AcceptButton=okay
        if kind!='Alert':
            cancel=Button();cancel.Text='Cancel';cancel.Size=Size(92,34);cancel.Location=Point(300,bottom);cancel.DialogResult=DialogResult.Cancel;cancel.FlatStyle=FlatStyle.Flat;cancel.BackColor=rgb(colors['paper']);cancel.ForeColor=dialog.ForeColor;cancel.FlatAppearance.BorderColor=rgb(colors['line']);dialog.Controls.Add(cancel);dialog.CancelButton=cancel
        else:dialog.CancelButton=okay
        dialog.ClientSize=Size(520,bottom+57)
        def focused(*_):
            dialog.Activate()
            if field is not None:field.Focus();field.SelectAll()
            else:okay.Focus()
        dialog.Shown+=focused;appearance.caption(dialog,theme,brand['name']);shade.Show(owner);shade.Enabled=False
        result=dialog.ShowDialog(owner)
        return result==DialogResult.OK or kind=='Alert',str(field.Text) if field is not None else ''
    finally:
        dialog.Dispose();shade.Dispose()
        if not owner.IsDisposed:owner.Activate()

def restore_input_focus(owner):
    """Return keyboard input to the WebView after the modal deferral completes."""
    if owner.IsDisposed or not owner.Enabled or not owner.Visible:return False
    browser=getattr(owner,'webview',None)
    if browser is None or browser.IsDisposed:return False
    browser.Select()
    return bool(browser.Focus())


def install(core,owner,brand_for,theme_for,*,show_fn=show,post=None,restore_focus=None):
    """Defer modal UI until after the WebView event callback has returned."""
    if post is None:
        from System import Action
        post=lambda callback:owner.BeginInvoke(Action(callback))
    def opening(sender,args):
        brand=brand_for(str(args.Uri))
        if not brand:return # An untrusted origin cannot create an app-branded dialog.
        deferral=args.GetDeferral()
        def display():
            try:
                if owner.IsDisposed:return
                kind=str(args.Kind);accepted,text=show_fn(owner,brand,kind,str(args.Message),str(args.DefaultText or ''),theme_for())
                if accepted:
                    if kind=='Prompt':args.ResultText=text
                    args.Accept()
            except Exception:
                log.error('A desktop dialog could not be displayed.')
            finally:
                deferral.Complete()
                if restore_focus is not None and not owner.IsDisposed:
                    def refocus():
                        try:restore_focus()
                        except Exception:log.error('Desktop keyboard focus could not be restored.')
                    try:post(refocus)
                    except Exception:log.error('Desktop keyboard focus could not be scheduled.')
        try:post(display)
        except Exception:deferral.Complete();log.error('A desktop dialog could not be scheduled.')
    core.ScriptDialogOpening+=opening;core.Settings.AreDefaultScriptDialogsEnabled=False
    return opening
