"""
🙈 Hide sensitive data in screenshots (ideas: Opkey data masking, Worksoft secure test data)

On a client's live system («client» site) every screenshot the tool takes blurs what's typed in the form and the rows
of tables (names, amounts, tax numbers…), while labels, headers, buttons and error messages stay readable — so a
report can be sent on without exposing the client's data. Off: MASK_SHOTS=0, or a «test» site.
"""
import os

MASK_JS = r"""
if (!document.getElementById('__nqmask')) {
  const s = document.createElement('style'); s.id = '__nqmask';
  s.textContent = `input:not([type=button]):not([type=submit]):not([type=checkbox]):not([type=radio]), textarea,
    .select2-selection__rendered, .select2-results__option, table tbody td, .dataTables_wrapper tbody td,
    .dx-datagrid-rowsview td, .info-box-number, .small-box h3 { filter: blur(5px) !important; }`;
  document.head.appendChild(s);
}
"""
UNMASK_JS = "const m = document.getElementById('__nqmask'); if (m) m.remove();"


def enabled():
    if os.getenv("MASK_SHOTS", "1") == "0":
        return False
    try:
        from engine.guard import read_only
        return read_only()
    except Exception:
        return False


def shot(driver, take):
    """take() = the real screenshot call; masked around it when needed"""
    if not enabled():
        return take()
    try:
        driver.execute_script(MASK_JS)
    except Exception:
        pass
    try:
        return take()
    finally:
        try:
            driver.execute_script(UNMASK_JS)
        except Exception:
            pass
