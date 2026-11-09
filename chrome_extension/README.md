# NQ Test Recorder (Chrome extension)

Record what you (or an implementation consultant) do on NQ ERP in your normal Chrome, and send it to the test
automation dashboard as a new test — like Worksoft Capture / Opkey's recorder.

1. On Railway set a variable `RECORDER_TOKEN` (any long text).
2. Chrome → `chrome://extensions` → turn on *Developer mode* → *Load unpacked* → pick this `chrome_extension` folder.
3. Open the ERP **add** page (e.g. a new cash receipt), click the extension, enter the dashboard link + the token + a
   test name, press **Start**, work on the screen normally (fields, item lines, windows, attachments).
4. Press **Send**. The test shows in the Test builder (and Automatic test), ready to try / save / schedule.
   Pressing «Save» on the ERP screen does **not** save: it only ends the recording.
