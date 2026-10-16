# Google Sheets Real-Time Sync Setup (Supports Sheet1 & Sheet2)

Your Google Sheet:
**https://docs.google.com/spreadsheets/d/1-J4aod-jEImTQ1QQDM9seK7oVqYpTxn9-Tzj2V-rMNQ/edit?usp=sharing**

- **Sheet1:** Standard Auto-Apply Jobs (logged by `RUN_APPLY.bat`)
- **Sheet2:** ⚡ Instant Live Radar Jobs (logged immediately by `RUN_LIVE_RADAR.bat` the moment HR posts)

---

### Step 1: Open Apps Script in Google Sheets
1. Open your Google Sheet link above.
2. In the top menu, click **Extensions** > **Apps Script**.

---

### Step 2: Paste this Code (Supports Sheet1 & Sheet2)
Delete whatever code is currently in the editor (`Code.gs`), and paste this:

```javascript
function doPost(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var data = JSON.parse(e.postData.contents);
  var targetName = (Array.isArray(data) ? (data[0] && data[0].sheet_name) : data.sheet_name) || "Sheet1";
  
  var sheet = ss.getSheetByName(targetName);
  if (!sheet) {
    sheet = ss.insertSheet(targetName);
  }
  
  // Set headers automatically on first run
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      "Apply Time",
      "Target Role",
      "Job Title",
      "Company",
      "HR Posted Time",
      "Status",
      "Notes / Reason",
      "Job Link"
    ]);
    sheet.getRange(1, 1, 1, 8)
      .setFontWeight("bold")
      .setBackground(targetName === "Sheet2" ? "#fce8e6" : "#e6f4ea");
    sheet.setFrozenRows(1);
  }
  
  function toRow(r) {
    return [
      r.timestamp || new Date().toLocaleString(),
      r.role || "-",
      r.title || "-",
      r.company || "-",
      r.posted_time || "Today",
      r.status || "applied",
      r.reason || "",
      r.job_url || ""
    ];
  }
  
  // Handles batch sync and single row sync
  if (Array.isArray(data)) {
    for (var i = 0; i < data.length; i++) {
      sheet.appendRow(toRow(data[i]));
    }
  } else {
    sheet.appendRow(toRow(data));
  }
  
  return ContentService.createTextOutput(JSON.stringify({"result": "success"}))
    .setMimeType(ContentService.MimeType.JSON);
}
```

---

### Step 3: Deploy as Web App
1. In the top right corner, click **Deploy** > **Manage deployments** (or **New deployment**).
2. Edit the existing deployment or click **New deployment** > gear icon ⚙️ > **Web app**.
3. Settings:
   - **Execute as**: `Me`
   - **Who has access**: `Anyone`
4. Click **Deploy**.
5. Copy the **Web app URL** and make sure it's in your `.env` file as `GOOGLE_SHEET_WEBHOOK_URL=...`.

---

### Step 4: Running the Bots
- **Standard Continuous Apply:** Double-click `RUN_APPLY.bat` -> logs to **Sheet1**.
- **⚡ Instant Live Radar (New HR Postings):** Double-click `RUN_LIVE_RADAR.bat` -> logs to **Sheet2**.
