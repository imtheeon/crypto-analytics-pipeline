/**
 * Google Apps Script timer for the crypto pipeline.
 *
 * GitHub's own cron fired once in about 12 hours for this repo, so this script presses "Run workflow" instead:
 * a time-driven trigger calls cryptoDispatchPipeline every 15 minutes. The workflow's cron line stays as a backup.
 *
 * Setup (Apps Script project "crypto-pipeline-timer"):
 *   Script Properties > CRYPTO_GITHUB_TOKEN = a fine-grained GitHub token for this repo only,
 *   with Actions: read and write, and an expiry. The token is never written in this file.
 */

const CRYPTO_REPO = 'imtheeon/crypto-analytics-pipeline';
const CRYPTO_WORKFLOW = 'crypto_pipeline.yml';
const CRYPTO_ALERT_EVERY_MS = 60 * 60 * 1000; // at most one failure email per hour; every failure is still logged

function cryptoDispatchPipeline() {
  const token = PropertiesService.getScriptProperties().getProperty('CRYPTO_GITHUB_TOKEN');
  if (!token) {
    cryptoAlert_('CRYPTO_GITHUB_TOKEN is missing from Script Properties. No run was started.');
    return;
  }
  const url = 'https://api.github.com/repos/' + CRYPTO_REPO + '/actions/workflows/' + CRYPTO_WORKFLOW + '/dispatches';
  let code, body;
  try {
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      payload: JSON.stringify({ ref: 'main' }),
      muteHttpExceptions: true, // non-2xx comes back as a response instead of throwing
    });
    code = response.getResponseCode();
    body = response.getContentText();
  } catch (e) {
    cryptoAlert_('The request to GitHub failed before a response (network or Apps Script error): ' + e);
    return;
  }
  console.log('dispatch ' + CRYPTO_WORKFLOW + ' on main -> HTTP ' + code);
  if (code < 200 || code >= 300) {
    // 401 usually means the token expired or was revoked; 403/404 usually means a wrong permission or repo.
    cryptoAlert_('GitHub answered HTTP ' + code + ', so no run was started.\n\n' + body.slice(0, 1000));
  }
}

function cryptoAlert_(message) {
  console.error(message);
  const props = PropertiesService.getScriptProperties();
  const last = Number(props.getProperty('CRYPTO_LAST_ALERT_MS') || 0);
  if (Date.now() - last < CRYPTO_ALERT_EVERY_MS) {
    console.log('Alert email skipped: one was already sent in the last hour.');
    return;
  }
  MailApp.sendEmail(Session.getEffectiveUser().getEmail(), 'crypto-pipeline-timer: workflow dispatch failed',
    message + '\n\nRepo: ' + CRYPTO_REPO + '\nLogs: Apps Script project crypto-pipeline-timer > Executions.');
  props.setProperty('CRYPTO_LAST_ALERT_MS', String(Date.now()));
}
