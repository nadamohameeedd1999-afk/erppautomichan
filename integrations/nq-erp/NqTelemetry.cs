// =====================================================================================================
//  NqTelemetry.cs — NQ ERP tells the test dashboard («مراقبة المواقع») about its own errors and version.
//  ASP.NET MVC 5 / .NET Framework 4.5+ · no NuGet package needed · never slows or breaks a request
//  (sent in the background, 5-second limit, every failure swallowed).
//
//  Setup (once per project, then per client only the link in Web.config):
//   1) Add this file to the project (e.g. App_Start/NqTelemetry.cs).
//   2) Web.config  <appSettings>:
//        <add key="NqTelemetryUrl" value="(the site's link from the dashboard: مراقبة المواقع ▸ ربط NQ ERP)" />
//        <add key="NqVersion" value="2026.11.21" />          (optional; without it: the DLL's version + build date)
//   3) App_Start/FilterConfig.cs  → RegisterGlobalFilters:   filters.Add(new NqTelemetryFilter());
//   4) Global.asax.cs:
//        Application_Start():   NqTelemetry.Started();          (last line)
//        protected void Application_Error() { NqTelemetry.Report(Server.GetLastError(), HttpContext.Current); }
//   5) Views/Shared/_Layout.cshtml (and the login layout) before </body>:  @Html.Raw(NqTelemetry.BrowserScript())
//  Empty NqTelemetryUrl = everything off.
//
//  Sent: error type + message (+ inner errors), the screen URL, the signed-in user NAME, the stack trace, the version.
//  Never sent: passwords, form fields, cookies, request bodies.
// =====================================================================================================
using System;
using System.Collections.Generic;
using System.Configuration;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Web;
using System.Web.Mvc;
using System.Web.Script.Serialization;

public static class NqTelemetry
{
    static readonly HttpClient Http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    static readonly string Url = (ConfigurationManager.AppSettings["NqTelemetryUrl"] ?? "").Trim();
    static readonly string Version = ConfigurationManager.AppSettings["NqVersion"] ?? typeof(NqTelemetry).Assembly.GetName().Version.ToString();
    static readonly string Build = BuildDate();

    static string BuildDate()
    {
        try { return File.GetLastWriteTime(typeof(NqTelemetry).Assembly.Location).ToString("yyyy-MM-dd HH:mm"); }
        catch { return ""; }
    }

    /// <summary>Application_Start: the app (re)started — deploy, IIS recycle or crash — and which version it runs.</summary>
    public static void Started()
    {
        Send(new Dictionary<string, object> { { "kind", "start" }, { "machine", Environment.MachineName } });
    }

    /// <summary>An exception on the server (from the MVC filter or Application_Error).</summary>
    public static void Report(Exception ex, HttpContext ctx)
    {
        if (ex == null || string.IsNullOrEmpty(Url)) return;
        var http = ex as HttpException;
        if (http != null && http.GetHttpCode() == 404) return;                 // missing pages are bots and old links, not errors
        if (ctx != null && ctx.Items["nq_telemetry_sent"] != null) return;     // the filter already sent it, Application_Error sees it again
        if (ctx != null) ctx.Items["nq_telemetry_sent"] = true;
        var msg = new StringBuilder(ex.Message);
        for (var inner = ex.InnerException; inner != null; inner = inner.InnerException)
            msg.Append(" ← ").Append(inner.GetType().Name).Append(": ").Append(inner.Message);
        var root = ex; while (root.InnerException != null) root = root.InnerException;
        string url = "", user = "";
        try
        {
            if (ctx != null)
            {
                url = ctx.Request.Url != null ? ctx.Request.Url.PathAndQuery : "";
                user = ctx.User != null && ctx.User.Identity != null ? ctx.User.Identity.Name : "";
            }
        }
        catch { }
        Send(new Dictionary<string, object> {
            { "kind", "server" }, { "type", root.GetType().FullName }, { "message", msg.ToString() },
            { "url", url }, { "user", user }, { "stack", ex.ToString() } });
    }

    static void Send(Dictionary<string, object> item)
    {
        if (string.IsNullOrEmpty(Url)) return;
        item["version"] = Version;
        item["build"] = Build;
        string body;
        try { body = Json.Serialize(item); } catch { return; }
        Task.Run(async () =>
        {
            try { using (await Http.PostAsync(Url, new StringContent(body, Encoding.UTF8, "application/json"))) { } }
            catch { }                                                          // the dashboard down must never matter to NQ ERP
        });
    }

    /// <summary>For _Layout.cshtml: JavaScript errors and AJAX calls that came back 500, from the user's browser.</summary>
    public static string BrowserScript()
    {
        if (string.IsNullOrEmpty(Url)) return "";
        string user = "";
        try { var c = HttpContext.Current; user = c != null && c.User != null && c.User.Identity != null ? c.User.Identity.Name : ""; } catch { }
        var cfg = Json.Serialize(new { url = Url, user = user, version = Version, build = Build });
        return @"<script>(function(c){var n=0,seen={};function send(o){if(n>=20)return;var k=o.kind+o.message+o.url;if(seen[k])return;seen[k]=1;n++;
o.user=c.user;o.version=c.version;o.build=c.build;o.url=o.url||location.pathname+location.search;var b=JSON.stringify(o);
try{if(navigator.sendBeacon&&navigator.sendBeacon(c.url,new Blob([b],{type:'text/plain'})))return}catch(e){}
try{var x=new XMLHttpRequest();x.open('POST',c.url,true);x.setRequestHeader('Content-Type','text/plain');x.send(b)}catch(e){}}
window.addEventListener('error',function(e){if(!e.message)return;send({kind:'js',type:'',message:e.message+' ('+(e.filename||'').split('/').pop()+':'+e.lineno+')',stack:e.error&&e.error.stack||''})});
window.addEventListener('unhandledrejection',function(e){var r=e.reason||{};send({kind:'js',type:'Promise',message:String(r.message||r),stack:r.stack||''})});
if(window.jQuery)jQuery(document).ajaxError(function(ev,x,s){if(!x||x.status<500)return;
send({kind:'ajax',type:'HTTP '+x.status,status:String(x.status),message:(s.type||'GET')+' '+(s.url||'').split('?')[0],url:location.pathname+location.search,response:String(x.responseText||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').slice(0,1500)})});
})(" + cfg + ");</script>";
    }
}

/// <summary>Exceptions inside controllers (MVC handles them before Application_Error when customErrors is on).</summary>
public class NqTelemetryFilter : IExceptionFilter
{
    public void OnException(ExceptionContext filterContext)
    {
        try { NqTelemetry.Report(filterContext.Exception, HttpContext.Current); } catch { }
    }
}
