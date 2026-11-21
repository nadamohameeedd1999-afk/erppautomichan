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
//   6) ZATCA (optional, where the e-invoice answer comes back — clearance / reporting):
//        NqTelemetry.Zatca(invoice.Number, "cleared" | "reported" | "warning" | "rejected" | "failed", messageFromZatca, invoice.Total);
//  Empty NqTelemetryUrl = everything off.
//
//  Also automatic once Started() runs:
//   • screen usage — how many times each screen (Controller/Action that returns a page) was opened, and by whom; every 10 min
//   • database health every 6 h, READ ONLY (SELECTs only) on the app's own connection string (Web.config
//     <add key="NqTelemetryDb" value="name of the connection string" />, else the first one): last full / log backup,
//     data + log size, recovery model, free disk, SQL Agent jobs failed in 24 h, the 5 slowest queries. A query the
//     hosting account isn't allowed to run is skipped and reported as «not allowed».
//
//  Sent: error type + message (+ inner errors), the screen URL, the signed-in user NAME, the stack trace, the version,
//  screen names + counts, ZATCA invoice numbers + statuses + ZATCA's message, the database numbers above.
//  Never sent: passwords, form fields, cookies, request bodies, table data.
// =====================================================================================================
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Configuration;
using System.Data.SqlClient;
using System.IO;
using System.Linq;
using System.Threading;
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

    static Timer _timer;
    static DateTime _lastDb = DateTime.MinValue;
    static readonly ConcurrentDictionary<string, ConcurrentDictionary<string, byte>> UsageUsers = new ConcurrentDictionary<string, ConcurrentDictionary<string, byte>>();
    static readonly ConcurrentDictionary<string, int> UsageCount = new ConcurrentDictionary<string, int>();
    static readonly ConcurrentDictionary<string, int> ZatcaOk = new ConcurrentDictionary<string, int>();
    static readonly ConcurrentQueue<Dictionary<string, object>> ZatcaWarnings = new ConcurrentQueue<Dictionary<string, object>>();

    /// <summary>Application_Start: the app (re)started — deploy, IIS recycle or crash — and which version it runs.
    /// Also starts the 10-minute flush (screen usage, ZATCA counts) and the 6-hour database check.</summary>
    public static void Started()
    {
        Send(new Dictionary<string, object> { { "kind", "start" }, { "machine", Environment.MachineName } });
        if (string.IsNullOrEmpty(Url) || _timer != null) return;
        _timer = new Timer(_ => Tick(), null, TimeSpan.FromMinutes(2), TimeSpan.FromMinutes(10));
    }

    static void Tick()
    {
        try { FlushUsage(); } catch { }
        try { FlushZatca(); } catch { }
        if (DateTime.Now - _lastDb > TimeSpan.FromHours(6))
        {
            _lastDb = DateTime.Now;
            try { DbHealth(); } catch { }
        }
    }

    /// <summary>One page opened (called by NqTelemetryFilter for actions that return a page).</summary>
    public static void Used(string screen, string user)
    {
        if (string.IsNullOrEmpty(Url) || string.IsNullOrEmpty(screen)) return;
        UsageCount.AddOrUpdate(screen, 1, (k, n) => n + 1);
        if (!string.IsNullOrEmpty(user)) UsageUsers.GetOrAdd(screen, k => new ConcurrentDictionary<string, byte>()).TryAdd(user, 0);
    }

    static void FlushUsage()
    {
        var keys = UsageCount.Keys.ToList();
        if (keys.Count == 0) return;
        var all = new Dictionary<string, object>();
        foreach (var k in keys)
        {
            int n; ConcurrentDictionary<string, byte> u;
            if (!UsageCount.TryRemove(k, out n)) continue;
            UsageUsers.TryRemove(k, out u);
            all[k] = new Dictionary<string, object> { { "n", n }, { "users", u == null ? new string[0] : u.Keys.Take(20).ToArray() } };
        }
        foreach (var chunk in all.Select((kv, i) => new { kv, i }).GroupBy(x => x.i / 80))      // keeps each report small
            Send(new Dictionary<string, object> { { "kind", "usage" }, { "screens", chunk.ToDictionary(x => x.kv.Key, x => x.kv.Value) } });
    }

    /// <summary>The answer ZATCA gave for an e-invoice. Rejected / failed are sent at once; the rest are counted every 10 minutes.</summary>
    public static void Zatca(string invoiceNo, string status, string message = "", decimal amount = 0)
    {
        if (string.IsNullOrEmpty(Url)) return;
        status = (status ?? "").Trim().ToLowerInvariant();
        var item = new Dictionary<string, object> { { "kind", "zatca" }, { "invoice", invoiceNo ?? "" }, { "status", status },
                                                    { "message", (message ?? "").Length > 800 ? message.Substring(0, 800) : (message ?? "") }, { "amount", amount } };
        if (status == "rejected" || status == "failed") { Send(item); return; }
        ZatcaOk.AddOrUpdate(status == "" ? "cleared" : status, 1, (k, n) => n + 1);
        if (status == "warning" && ZatcaWarnings.Count < 20) ZatcaWarnings.Enqueue(item);
    }

    static void FlushZatca()
    {
        var counts = new Dictionary<string, object>();
        foreach (var k in ZatcaOk.Keys.ToList()) { int n; if (ZatcaOk.TryRemove(k, out n)) counts[k] = n; }
        var warn = new List<object>();
        Dictionary<string, object> w;
        while (ZatcaWarnings.TryDequeue(out w)) warn.Add(w);
        if (counts.Count > 0 || warn.Count > 0)
            Send(new Dictionary<string, object> { { "kind", "zatca" }, { "counts", counts }, { "warnings", warn } });
    }

    /// <summary>Read-only health of the app's own database (SELECTs only; each one skipped if the account isn't allowed).</summary>
    public static void DbHealth()
    {
        var name = ConfigurationManager.AppSettings["NqTelemetryDb"];
        ConnectionStringSettings css = null;
        if (!string.IsNullOrEmpty(name)) css = ConfigurationManager.ConnectionStrings[name];
        if (css == null)
            css = ConfigurationManager.ConnectionStrings.Cast<ConnectionStringSettings>().FirstOrDefault(c => c.Name != "LocalSqlServer" && !string.IsNullOrEmpty(c.ConnectionString));
        if (css == null) return;
        var d = new Dictionary<string, object> { { "kind", "db" } };
        try
        {
            using (var cn = new SqlConnection(css.ConnectionString))
            {
                cn.Open();
                One(cn, d, "database", "SELECT DB_NAME()");
                One(cn, d, "backup_full", "SELECT CONVERT(varchar(16), MAX(backup_finish_date), 120) FROM msdb.dbo.backupset WHERE database_name = DB_NAME() AND type = 'D'");
                One(cn, d, "backup_log", "SELECT CONVERT(varchar(16), MAX(backup_finish_date), 120) FROM msdb.dbo.backupset WHERE database_name = DB_NAME() AND type = 'L'");
                One(cn, d, "data_mb", "SELECT CAST(SUM(CASE WHEN type = 0 THEN size ELSE 0 END) * 8 / 1024.0 AS decimal(12,1)) FROM sys.database_files");
                One(cn, d, "log_mb", "SELECT CAST(SUM(CASE WHEN type = 1 THEN size ELSE 0 END) * 8 / 1024.0 AS decimal(12,1)) FROM sys.database_files");
                One(cn, d, "recovery", "SELECT recovery_model_desc FROM sys.databases WHERE name = DB_NAME()");
                One(cn, d, "disk_free_gb", "SELECT TOP 1 CAST(available_bytes / 1073741824.0 AS decimal(12,1)) FROM sys.dm_os_volume_stats(DB_ID(), 1)");
                One(cn, d, "jobs_failed_24h", "SELECT COUNT(*) FROM msdb.dbo.sysjobhistory WHERE run_status = 0 AND step_id = 0 AND msdb.dbo.agent_datetime(run_date, run_time) > DATEADD(day, -1, GETDATE())");
                One(cn, d, "sql_version", "SELECT LEFT(@@VERSION, CHARINDEX(CHAR(10), @@VERSION + CHAR(10)) - 1)");
                try
                {
                    var slow = new List<object>();
                    using (var c = new SqlCommand(@"SELECT TOP 5 SUBSTRING(t.text, 1, 300), s.execution_count, s.total_elapsed_time / s.execution_count / 1000
                        FROM sys.dm_exec_query_stats s CROSS APPLY sys.dm_exec_sql_text(s.sql_handle) t
                        WHERE t.dbid = DB_ID() ORDER BY s.total_elapsed_time / s.execution_count DESC", cn) { CommandTimeout = 20 })
                    using (var r = c.ExecuteReader())
                        while (r.Read()) slow.Add(new Dictionary<string, object> { { "query", r.GetString(0) }, { "count", r.GetValue(1) }, { "avg_ms", r.GetValue(2) } });
                    d["slow"] = slow;
                }
                catch (Exception ex) { d["slow_error"] = ex.Message; }
            }
        }
        catch (Exception ex) { d["error"] = ex.Message; }
        Send(d);
    }

    static void One(SqlConnection cn, Dictionary<string, object> d, string key, string sql)
    {
        try
        {
            using (var c = new SqlCommand(sql, cn) { CommandTimeout = 15 })
            {
                var v = c.ExecuteScalar();
                d[key] = v == null || v == DBNull.Value ? null : (v is decimal || v is int || v is long ? v : (object)v.ToString());
            }
        }
        catch (Exception ex) { d[key + "_error"] = ex.Message; }
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

/// <summary>Exceptions inside controllers (MVC handles them before Application_Error when customErrors is on),
/// and screen usage: every action that returns a page counts as one opening of that screen.</summary>
public class NqTelemetryFilter : IExceptionFilter, IActionFilter
{
    public void OnException(ExceptionContext filterContext)
    {
        try { NqTelemetry.Report(filterContext.Exception, HttpContext.Current); } catch { }
    }

    public void OnActionExecuting(ActionExecutingContext filterContext) { }

    public void OnActionExecuted(ActionExecutedContext filterContext)
    {
        try
        {
            if (filterContext.IsChildAction || !(filterContext.Result is ViewResult)) return;
            var rd = filterContext.RouteData.Values;
            var user = filterContext.HttpContext.User != null && filterContext.HttpContext.User.Identity != null ? filterContext.HttpContext.User.Identity.Name : "";
            NqTelemetry.Used(rd["controller"] + "/" + rd["action"], user);
        }
        catch { }
    }
}
