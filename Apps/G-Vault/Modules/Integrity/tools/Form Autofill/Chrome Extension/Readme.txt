Rutgers Integrity Form Helper — automatic outcome PDF attachment

UPDATE
Open chrome://extensions and click Reload for Rutgers Integrity Form Helper. Version 0.2.0 adds optional local-app access; no other websites are added.

USE
1. Open Academic Integrity through its launcher and keep it running.
2. Review the wording and create the signed final. Export and download a NEW reporting JSON. Older JSON files do not contain the PDF link.
3. Open the Rutgers final reporting form in Chrome and sign in yourself.
4. Open the helper, choose the JSON, and confirm the student.
5. Check “I authorize attaching this student’s linked outcome PDF to the Rutgers form.” Allow Chrome’s local-app permission if prompted.
6. Click Fill form. The helper retrieves the specific PDF from the running local app, verifies its SHA-256 hash, and adds it to Supporting Documentation. Existing attachments are retained.
7. Check every answer and confirm that the correct PDF appears. Add any other evidence manually. Submit the form yourself.

Draft exports cannot automatically attach a PDF. If the app restarts, the letter changes, the PDF changes, or the letter is deleted, export a fresh JSON. The helper supports automatic attachment up to 25 MB; larger files can be attached manually. The online form’s own upload limits still apply.

Checking the attachment box authorizes placing the PDF on the Rutgers form; the form may upload it immediately. Nothing clicks Submit. Without the box checked, the helper fills answers only. Closing the popup discards loaded data. JSON exports contain private student data and a private link to their PDF: keep them local.

INSTALL FIRST TIME
Open chrome://extensions, enable Developer mode, choose Load unpacked, and select this Chrome Extension folder. Pin Rutgers Integrity Form Helper from Chrome’s extension menu.
