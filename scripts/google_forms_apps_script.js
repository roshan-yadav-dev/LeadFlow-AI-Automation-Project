/**
 * LeadFlow AI — Google Forms / Sheets Webhook Integration Script
 *
 * This Google Apps Script binds to a Google Spreadsheet linked to a Google Form.
 * When a form submission occurs, the installable 'onFormSubmit' trigger runs this script,
 * packages the submitted answers with metadata, and securely dispatches them to the
 * LeadFlow AI webhook endpoint.
 *
 * INSTALLATION & SETUP INSTRUCTIONS:
 * ----------------------------------------------------------------------------
 * 1. Link your Google Form to a Google Spreadsheet:
 *    - In your Google Form, open the "Responses" tab.
 *    - Click "Link to Sheets" and choose or create a target spreadsheet.
 *
 * 2. Open the Script Editor:
 *    - In the linked Google Sheet, click "Extensions" > "Apps Script".
 *    - Delete any default code in Code.gs and paste the contents of this file.
 *    - Name the project "LeadFlow Form Webhook".
 *
 * 3. Configure Script Properties (DO NOT HARDCODE SECRETS IN SCRIPT CODE):
 *    - In the left sidebar of the Apps Script editor, click the gear icon ("Project Settings").
 *    - Scroll down to "Script Properties" and click "Add script property".
 *    - Add property 1:
 *        Property: LEADFLOW_WEBHOOK_URL
 *        Value: https://<your-server-domain>/api/v1/leads/webhook/forms
 *    - Add property 2:
 *        Property: LEADFLOW_WEBHOOK_SECRET
 *        Value: <YOUR_WEBHOOK_SECRET> (same value as WEBHOOK_SECRET in LeadFlow .env)
 *    - Click "Save script properties".
 *
 * 4. Create the Installable Trigger:
 *    - In the left sidebar, click the alarm clock icon ("Triggers").
 *    - Click "+ Add Trigger" in the bottom-right corner.
 *    - Choose which function to run: handleFormSubmit
 *    - Choose which deployment should run: Head
 *    - Select event source: From spreadsheet
 *    - Select event type: On form submit
 *    - Failure notification settings: Notify me daily (or immediately)
 *    - Click "Save" and authorize Google permissions when prompted.
 *
 * 5. Test the Setup:
 *    - Submit a test response through your live Google Form.
 *    - Open Apps Script > "Executions" to verify execution logs and HTTP status.
 * ----------------------------------------------------------------------------
 */

function handleFormSubmit(e) {
  if (!e) {
    Logger.log("Execution aborted: No event object received. Ensure this function runs via the onFormSubmit trigger.");
    return;
  }

  var scriptProperties = PropertiesService.getScriptProperties();
  var webhookUrl = scriptProperties.getProperty("LEADFLOW_WEBHOOK_URL");
  var webhookSecret = scriptProperties.getProperty("LEADFLOW_WEBHOOK_SECRET");

  if (!webhookUrl || !webhookSecret) {
    Logger.log("Configuration error: LEADFLOW_WEBHOOK_URL or LEADFLOW_WEBHOOK_SECRET is missing in Script Properties.");
    return;
  }

  try {
    var range = e.range;
    var sheet = range ? range.getSheet() : null;
    var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();

    var spreadsheetId = spreadsheet ? spreadsheet.getId() : "unknown_spreadsheet";
    var sheetId = sheet ? sheet.getSheetId() : 0;
    var sheetName = sheet ? sheet.getName() : "Form Responses";
    var rowNumber = range ? range.getRow() : 0;

    // Generate a stable, deterministic submission identifier based on sheet context
    var submissionId = spreadsheetId + "_" + sheetId + "_row_" + rowNumber;

    // Extract namedValues (Object with question titles -> array of answer strings)
    var namedValues = e.namedValues || {};

    // Build normalized payload
    var payload = {
      submission_id: submissionId,
      spreadsheet_id: spreadsheetId,
      sheet_id: sheetId,
      sheet_name: sheetName,
      row_number: rowNumber,
      timestamp: new Date().toISOString(),
      named_values: namedValues
    };

    var options = {
      method: "post",
      contentType: "application/json",
      headers: {
        "X-Webhook-Secret": webhookSecret
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    Logger.log("Dispatching submission " + submissionId + " to LeadFlow AI webhook...");
    var response = UrlFetchApp.fetch(webhookUrl, options);
    var statusCode = response.getResponseCode();

    if (statusCode >= 200 && statusCode < 300) {
      Logger.log("LeadFlow AI webhook succeeded with HTTP " + statusCode + " for submission " + submissionId);
    } else {
      Logger.log("LeadFlow AI webhook returned non-2xx status code: " + statusCode + " for submission " + submissionId);
    }
  } catch (error) {
    // Log safe operational error without exposing secrets or token data
    Logger.log("Error dispatching form submission to LeadFlow AI: " + error.toString());
  }
}
