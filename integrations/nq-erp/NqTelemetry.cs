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
//   • the books once a day, READ ONLY, with checks written HERE (nothing is ever sent from the dashboard to run):
//     unbalanced journal entries, the trial balance total, entries without lines, lines with debit and credit together
//     or negative, lines on parent / deleted / inactive accounts, customer-account lines without the customer, future dates
//   • the database structure (table → columns + types) once a day, or when it changes — the dashboard compares it with
//     the test site's to find what an update script didn't create here («Invalid column name» before it happens)
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
    static readonly string Build = BuildDate();
    static readonly string Version = ConfigurationManager.AppSettings["NqVersion"] ?? DllVersion();

    static string DllVersion()
    {
        var v = typeof(NqTelemetry).Assembly.GetName().Version.ToString();
        return v == "1.0.0.0" || v == "0.0.0.0" ? Build : v;                  // the default AssemblyInfo says nothing: the build date tells versions apart
    }

    static string Clip(string s, int n) { return s == null ? "" : s.Length > n ? s.Substring(0, n) : s; }

    /// <summary>Keeps adding items to a part until ~14,000 characters (the dashboard refuses a report over 20,000).</summary>
    static List<Dictionary<string, object>> Parts(IEnumerable<KeyValuePair<string, object>> items, Func<object, int> size)
    {
        var parts = new List<Dictionary<string, object>>();
        var cur = new Dictionary<string, object>();
        int n = 0;
        foreach (var kv in items)
        {
            int s = kv.Key.Length + size(kv.Value) + 10;
            if (cur.Count > 0 && n + s > 14000) { parts.Add(cur); cur = new Dictionary<string, object>(); n = 0; }
            cur[kv.Key] = kv.Value;
            n += s;
        }
        if (cur.Count > 0) parts.Add(cur);
        return parts;
    }

    static string BuildDate()
    {
        try { return File.GetLastWriteTime(typeof(NqTelemetry).Assembly.Location).ToString("yyyy-MM-dd HH:mm"); }
        catch { return ""; }
    }

    static Timer _timer;
    static DateTime _lastDb = DateTime.MinValue, _lastBooks = DateTime.MinValue, _lastSchema = DateTime.MinValue;
    static string _schemaHash = "";
    static readonly ConcurrentDictionary<string, ConcurrentDictionary<string, byte>> UsageUsers = new ConcurrentDictionary<string, ConcurrentDictionary<string, byte>>();
    static readonly ConcurrentDictionary<string, int> UsageCount = new ConcurrentDictionary<string, int>();
    static readonly ConcurrentDictionary<string, int> ZatcaOk = new ConcurrentDictionary<string, int>();
    static readonly ConcurrentQueue<Dictionary<string, object>> ZatcaWarnings = new ConcurrentQueue<Dictionary<string, object>>();

    /// <summary>Application_Start: the app (re)started — deploy, IIS recycle or crash — and which version it runs.
    /// Also starts the 10-minute flush (screen usage, ZATCA counts) and the 6-hour database check.</summary>
    public static void Started()
    {
        try
        {
            if (string.IsNullOrEmpty(Url)) return;
            // .NET 4.5–4.6 default to TLS 1.0: an https dashboard would refuse every report. |= only ADDS 1.2, nothing the app uses is removed
            System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
            string machine = "";
            try { machine = Environment.MachineName; } catch { }
            Send(new Dictionary<string, object> { { "kind", "start" }, { "machine", machine } });
            if (_timer == null) _timer = new Timer(_ => Tick(), null, TimeSpan.FromMinutes(2), TimeSpan.FromMinutes(10));
        }
        catch { }
    }

    static int _ticking;

    static void Tick()
    {
        if (Interlocked.Exchange(ref _ticking, 1) == 1) return;          // a slow round (big database) never overlaps the next one
        try { TickCore(); } finally { Interlocked.Exchange(ref _ticking, 0); }
    }

    static void TickCore()
    {
        try { FlushUsage(); } catch { }
        try { FlushZatca(); } catch { }
        if (DateTime.Now - _lastDb > TimeSpan.FromHours(6))
        {
            _lastDb = DateTime.Now;
            try { DbHealth(); } catch { }
        }
        // the books: at night (0–6) — or any time when they haven't run for two days
        if (DateTime.Now - _lastBooks > TimeSpan.FromHours(24) && (DateTime.Now.Hour < 6 || DateTime.Now - _lastBooks > TimeSpan.FromHours(48)))
        {
            _lastBooks = DateTime.Now;
            // the app pool recycles several times a day on shared hosting: remember the last run on disk, or the heavy checks
            // would run 2 minutes after every recycle, at peak time (App_Data writes don't restart the app; no file = 1601 = run)
            string stamp = null;
            try { stamp = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "App_Data", "nq_books.stamp"); } catch { }
            if (stamp == null || DateTime.Now - File.GetLastWriteTime(stamp) > TimeSpan.FromHours(24))
            {
                try { if (stamp != null) { Directory.CreateDirectory(Path.GetDirectoryName(stamp)); File.WriteAllText(stamp, ""); } } catch { }
                try { Books(); } catch { }
            }
        }
        try { Schema(); } catch { }
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
        foreach (var part in Parts(all, v => 40 + ((string[])((Dictionary<string, object>)v)["users"]).Sum(u => u.Length + 3)))
            Send(new Dictionary<string, object> { { "kind", "usage" }, { "screens", part } });
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
        var css = Conn();
        if (css == null) return;
        var d = new Dictionary<string, object> { { "kind", "db" } };
        try
        {
            using (var cn = new SqlConnection(css))
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

    static string Conn()
    {
        var name = ConfigurationManager.AppSettings["NqTelemetryDb"];
        ConnectionStringSettings css = null;
        if (!string.IsNullOrEmpty(name)) css = ConfigurationManager.ConnectionStrings[name];
        css = css ?? ConfigurationManager.ConnectionStrings.Cast<ConnectionStringSettings>().FirstOrDefault(c => c.Name != "LocalSqlServer" && !string.IsNullOrEmpty(c.ConnectionString));
        if (css == null) return null;
        try
        {   // an Entity Framework (EDMX) string: metadata=…;provider connection string="…" — the SQL part is inside
            var b = new System.Data.Common.DbConnectionStringBuilder { ConnectionString = css.ConnectionString };
            if (b.ContainsKey("provider connection string")) return (string)b["provider connection string"];
        }
        catch { }
        return css.ConnectionString;
    }

    // key, then the query with the IsDeleted columns, then the same without them (older databases). Each returns ONE number;
    // 0 = fine (tb_diff: the trial balance difference, fine under 0.01).
    static readonly string[][] BookChecks = {
        new[] { "unbalanced",
            "SELECT COUNT(*) FROM (SELECT je.Id FROM JournalEntry je JOIN JournalEntryDetail d ON d.JournalEntryId = je.Id WHERE ISNULL(je.IsDeleted,0) = 0 AND ISNULL(d.IsDeleted,0) = 0 GROUP BY je.Id HAVING ABS(SUM(ISNULL(d.Debit,0)) - SUM(ISNULL(d.Credit,0))) > 0.005) z",
            "SELECT COUNT(*) FROM (SELECT je.Id FROM JournalEntry je JOIN JournalEntryDetail d ON d.JournalEntryId = je.Id GROUP BY je.Id HAVING ABS(SUM(ISNULL(d.Debit,0)) - SUM(ISNULL(d.Credit,0))) > 0.005) z" },
        new[] { "tb_diff",
            "SELECT CAST(ISNULL(SUM(ISNULL(d.Debit,0)) - SUM(ISNULL(d.Credit,0)), 0) AS decimal(18,2)) FROM JournalEntryDetail d JOIN JournalEntry je ON je.Id = d.JournalEntryId WHERE ISNULL(je.IsDeleted,0) = 0 AND ISNULL(d.IsDeleted,0) = 0",
            "SELECT CAST(ISNULL(SUM(ISNULL(d.Debit,0)) - SUM(ISNULL(d.Credit,0)), 0) AS decimal(18,2)) FROM JournalEntryDetail d" },
        new[] { "empty",
            "SELECT COUNT(*) FROM JournalEntry je WHERE ISNULL(je.IsDeleted,0) = 0 AND NOT EXISTS (SELECT 1 FROM JournalEntryDetail d WHERE d.JournalEntryId = je.Id AND ISNULL(d.IsDeleted,0) = 0)",
            "SELECT COUNT(*) FROM JournalEntry je WHERE NOT EXISTS (SELECT 1 FROM JournalEntryDetail d WHERE d.JournalEntryId = je.Id)" },
        new[] { "bad_lines",
            "SELECT COUNT(*) FROM JournalEntryDetail d WHERE ISNULL(d.IsDeleted,0) = 0 AND ((ISNULL(d.Debit,0) <> 0 AND ISNULL(d.Credit,0) <> 0) OR d.Debit < 0 OR d.Credit < 0)",
            "SELECT COUNT(*) FROM JournalEntryDetail d WHERE (ISNULL(d.Debit,0) <> 0 AND ISNULL(d.Credit,0) <> 0) OR d.Debit < 0 OR d.Credit < 0" },
        new[] { "parent_lines",
            "SELECT COUNT(*) FROM JournalEntryDetail d JOIN JournalEntry je ON je.Id = d.JournalEntryId WHERE ISNULL(je.IsDeleted,0) = 0 AND ISNULL(d.IsDeleted,0) = 0 AND EXISTS (SELECT 1 FROM ChartOfAccount c WHERE c.ParentId = d.AccountId AND ISNULL(c.IsDeleted,0) = 0)",
            "SELECT COUNT(*) FROM JournalEntryDetail d WHERE EXISTS (SELECT 1 FROM ChartOfAccount c WHERE c.ParentId = d.AccountId)" },
        new[] { "dead_account_lines",
            "SELECT COUNT(*) FROM JournalEntryDetail d JOIN JournalEntry je ON je.Id = d.JournalEntryId JOIN ChartOfAccount a ON a.Id = d.AccountId WHERE ISNULL(je.IsDeleted,0) = 0 AND ISNULL(d.IsDeleted,0) = 0 AND (ISNULL(a.IsDeleted,0) = 1 OR a.IsActive = 0)",
            "SELECT COUNT(*) FROM JournalEntryDetail d JOIN ChartOfAccount a ON a.Id = d.AccountId WHERE a.IsActive = 0" },
        new[] { "customer_lines",
            "SELECT COUNT(*) FROM JournalEntryDetail d JOIN JournalEntry je ON je.Id = d.JournalEntryId JOIN ChartOfAccount a ON a.Id = d.AccountId WHERE ISNULL(je.IsDeleted,0) = 0 AND ISNULL(d.IsDeleted,0) = 0 AND a.IsCustomer = 1 AND ISNULL(d.CustomerId,0) = 0",
            "SELECT COUNT(*) FROM JournalEntryDetail d JOIN ChartOfAccount a ON a.Id = d.AccountId WHERE a.IsCustomer = 1 AND ISNULL(d.CustomerId,0) = 0" },
        new[] { "future",
            "SELECT COUNT(*) FROM JournalEntry je WHERE ISNULL(je.IsDeleted,0) = 0 AND je.Date > DATEADD(day, 1, GETDATE())",
            "SELECT COUNT(*) FROM JournalEntry je WHERE je.Date > DATEADD(day, 1, GETDATE())" },
    };

    /// <summary>The books, read only, once a day (checks fixed in this file).</summary>
    public static void Books()
    {
        var css = Conn();
        if (css == null) return;
        var res = new Dictionary<string, object>();
        var na = new Dictionary<string, object>();
        using (var cn = new SqlConnection(css))
        {
            try { cn.Open(); }
            catch (Exception ex)
            {
                Send(new Dictionary<string, object> { { "kind", "books" }, { "checks", res }, { "not_allowed", new Dictionary<string, object> { { "all", Clip(ex.Message, 200) } } } });
                return;
            }
            foreach (var c in BookChecks)
            {
                string err = null;
                for (int i = 1; i < c.Length; i++)
                {
                    try
                    {
                        using (var cmd = new SqlCommand(c[i], cn) { CommandTimeout = 120 })
                        {
                            var v = cmd.ExecuteScalar();
                            res[c[0]] = v == null || v == DBNull.Value ? 0 : v;
                            err = null;
                            break;
                        }
                    }
                    // only an older database without IsDeleted («Invalid column name», 207) may use the query without it:
                    // after a timeout or a lock it would count deleted entries and raise a false alarm
                    catch (SqlException ex) { err = ex.Message; if (ex.Number != 207) break; }
                    catch (Exception ex) { err = ex.Message; break; }
                }
                if (err != null) na[c[0]] = err.Length > 200 ? err.Substring(0, 200) : err;
            }
        }
        Send(new Dictionary<string, object> { { "kind", "books" }, { "checks", res }, { "not_allowed", na } });
    }

    /// <summary>table → "column:type,…" from INFORMATION_SCHEMA, sent in parts when it changed (or once a day).</summary>
    public static void Schema()
    {
        var css = Conn();
        if (css == null) return;
        var tables = new SortedDictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
        using (var cn = new SqlConnection(css))
        {
            cn.Open();
            using (var cmd = new SqlCommand("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' ORDER BY TABLE_NAME, ORDINAL_POSITION", cn) { CommandTimeout = 60 })
            using (var r = cmd.ExecuteReader())
                while (r.Read())
                {
                    List<string> cols;
                    if (!tables.TryGetValue(r.GetString(0), out cols)) tables[r.GetString(0)] = cols = new List<string>();
                    cols.Add(r.GetString(1) + ":" + r.GetString(2));
                }
        }
        var flat = tables.ToDictionary(t => t.Key, t => string.Join(",", t.Value));
        string hash;
        using (var sha = System.Security.Cryptography.SHA1.Create())
            hash = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(string.Join("|", flat.Select(kv => kv.Key + "=" + kv.Value))))).Replace("-", "").Substring(0, 16);
        if (hash == _schemaHash && DateTime.Now - _lastSchema < TimeSpan.FromHours(24)) return;
        _schemaHash = hash;
        _lastSchema = DateTime.Now;
        var parts = Parts(flat.Select(kv => new KeyValuePair<string, object>(kv.Key, Clip(kv.Value, 8000))), v => ((string)v).Length);
        for (int p = 0; p < parts.Count; p++)
            Send(new Dictionary<string, object> { { "kind", "schema" }, { "hash", hash }, { "part", p }, { "parts", parts.Count }, { "tables", parts[p] } });
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
        try { ReportCore(ex, ctx); } catch { }                                 // inside Application_Error: must never hide the real error
    }

    static void ReportCore(Exception ex, HttpContext ctx)
    {
        if (ex == null || string.IsNullOrEmpty(Url)) return;
        var http = ex as HttpException;
        // 4xx = bots, old links, dangerous paths, expired sessions — not bugs (and they'd fill the alerts)
        if (http != null && http.GetHttpCode() >= 400 && http.GetHttpCode() < 500) return;
        if (ex is HttpRequestValidationException || ex.GetType().Name == "HttpAntiForgeryException") return;   // by name: its assembly differs between MVC versions
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
                url = ctx.Request.Url != null ? ctx.Request.Url.AbsolutePath : "";   // no query string: it can carry reset / confirmation tokens
                user = ctx.User != null && ctx.User.Identity != null ? ctx.User.Identity.Name : "";
            }
        }
        catch { }
        Send(new Dictionary<string, object> {
            { "kind", "server" }, { "type", root.GetType().FullName }, { "message", Clip(msg.ToString(), 1000) },
            { "url", Clip(url, 300) }, { "user", Clip(user, 80) }, { "stack", Clip(ex.ToString(), 5000) } });     // the dashboard refuses a report over 20 KB
    }

    static int _minute, _sentThisMinute;
    static readonly object _rateLock = new object();

    static void Send(Dictionary<string, object> item)
    {
        if (string.IsNullOrEmpty(Url)) return;
        lock (_rateLock)
        {   // an error storm (the database down → every request throws) must not pile up thousands of posts: 40 a minute at most
            int m = (int)(DateTime.UtcNow.Ticks / TimeSpan.TicksPerMinute);
            if (m != _minute) { _minute = m; _sentThisMinute = 0; }
            if (++_sentThisMinute > 40) return;
        }
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

    /// <summary>The link the page's script uses: «…/api/telemetry/b/» + a one-way hash of the server token — anyone can read
    /// the page, so the real token (which may send the version, the database, the books) never goes into it.</summary>
    static string BrowserUrl()
    {
        int i = Url.LastIndexOf("/api/telemetry/", StringComparison.OrdinalIgnoreCase);
        if (i < 0) return "";
        var token = Url.Substring(i + "/api/telemetry/".Length).Trim('/');
        if (token.Length == 0 || token.Contains("/")) return "";
        using (var sha = System.Security.Cryptography.SHA256.Create())
            return Url.Substring(0, i) + "/api/telemetry/b/" + BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(token))).Replace("-", "").ToLowerInvariant().Substring(0, 32);
    }

    /// <summary>For _Layout.cshtml: JavaScript errors and AJAX calls that came back 500, from the user's browser.</summary>
    public static string BrowserScript()
    {
        if (string.IsNullOrEmpty(Url)) return "";
        string user = "";
        try { var c = HttpContext.Current; user = c != null && c.User != null && c.User.Identity != null ? c.User.Identity.Name : ""; } catch { }
        var burl = BrowserUrl();
        if (burl == "") return "";
        var cfg = Json.Serialize(new { url = burl, user = user, version = Version, build = Build });
        return @"<script>(function(c){var n=0,seen={};function send(o){if(n>=20)return;var k=o.kind+o.message+o.url;if(seen[k])return;seen[k]=1;n++;
o.user=c.user;o.version=c.version;o.build=c.build;o.url=o.url||location.pathname;var b=JSON.stringify(o);
try{if(navigator.sendBeacon&&navigator.sendBeacon(c.url,new Blob([b],{type:'text/plain'})))return}catch(e){}
try{var x=new XMLHttpRequest();x.open('POST',c.url,true);x.setRequestHeader('Content-Type','text/plain');x.send(b)}catch(e){}}
window.addEventListener('error',function(e){if(!e.message||e.message==='Script error.')return;send({kind:'js',type:'',message:String(e.message).slice(0,1000)+' ('+(e.filename||'').split('/').pop()+':'+e.lineno+')',stack:String(e.error&&e.error.stack||'').slice(0,5000)})});
window.addEventListener('unhandledrejection',function(e){var r=e.reason||{};send({kind:'js',type:'Promise',message:String(r.message||r),stack:r.stack||''})});
if(window.jQuery)jQuery(document).ajaxError(function(ev,x,s){if(!x||x.status<500)return;
send({kind:'ajax',type:'HTTP '+x.status,status:String(x.status),message:(s.type||'GET')+' '+(s.url||'').split('?')[0],url:location.pathname,response:String(x.responseText||'').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').slice(0,300)})});
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
            var ad = filterContext.ActionDescriptor;                       // real names, not the URL's spelling (invoice/ = Invoice/Index)
            var area = filterContext.RouteData.DataTokens["area"] as string;
            var user = filterContext.HttpContext.User != null && filterContext.HttpContext.User.Identity != null ? filterContext.HttpContext.User.Identity.Name : "";
            NqTelemetry.Used((string.IsNullOrEmpty(area) ? "" : area + "/") + ad.ControllerDescriptor.ControllerName + "/" + ad.ActionName, user);
        }
        catch { }
    }
}
