(function () {
  'use strict';

  var canvas = document.getElementById('mm-overview-chart');
  if (!canvas) { return; }

  /* ── Config injected via data attributes on the canvas element ─────────── */
  var DATA_URL      = canvas.dataset.pollUrl;
  var initialRed    = parseInt(canvas.dataset.red,   10) || 0;
  var initialGreen  = parseInt(canvas.dataset.green, 10) || 0;
  var initialAmber  = parseInt(canvas.dataset.amber, 10) || 0;

  /* ── Chart initialisation ────────────────────────────────────────────────── */
  window._mmChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Needs attention', 'All clear', 'Manual check'],
      datasets: [{
        data: [initialRed, initialGreen, initialAmber],
        backgroundColor: ['#d4351c', '#00703c', '#f47738'],
        borderWidth: 2,
        borderColor: '#ffffff'
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              return ' ' + ctx.label + ': ' + ctx.parsed +
                ' task' + (ctx.parsed !== 1 ? 's' : '');
            }
          }
        }
      },
      cutout: '62%'
    }
  });

  /* ── HTML helpers ───────────────────────────────────────────────────────── */
  function esc(str) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(str || '')));
    return d.innerHTML;
  }

  function checkStatusTag(status) {
    if (status === 'success') return '<strong class="govuk-tag govuk-tag--green">Passing</strong>';
    if (status === 'failure' || status === 'error') return '<strong class="govuk-tag govuk-tag--red">Failing</strong>';
    if (status === 'pending') return '<strong class="govuk-tag govuk-tag--yellow">Pending</strong>';
    return '<strong class="govuk-tag govuk-tag--grey">Unknown</strong>';
  }

  function tableWrap(headers, bodyRows) {
    var ths = headers.map(function (h) {
      return '<th scope="col" class="govuk-table__header">' + esc(h) + '</th>';
    }).join('');
    return '<table class="govuk-table govuk-!-margin-bottom-0">' +
      '<thead class="govuk-table__head"><tr class="govuk-table__row">' + ths + '</tr></thead>' +
      '<tbody class="govuk-table__body">' + bodyRows + '</tbody></table>';
  }

  function buildTableHTML(task) {
    if (!task.messages || task.messages.length === 0) { return ''; }
    var rows = '';
    if (task.table_type === 'dependabot') {
      task.messages.forEach(function (msg) {
        rows += '<tr class="govuk-table__row">' +
          '<td class="govuk-table__cell"><a class="govuk-link" href="' + esc(msg.link) + '" target="_blank" rel="noopener noreferrer">' + esc(msg.text) + '</a></td>' +
          '<td class="govuk-table__cell govuk-!-white-space-nowrap">' + esc(msg.time) + '</td>' +
          '<td class="govuk-table__cell">' + checkStatusTag(msg.check_status) + '</td>' +
          '</tr>';
      });
      return tableWrap(['PR', 'Updated', 'CI status'], rows);
    } else if (task.table_type === 'workflows') {
      task.messages.forEach(function (msg) {
        rows += '<tr class="govuk-table__row">' +
          '<td class="govuk-table__cell"><a class="govuk-link" href="' + esc(msg.link) + '" target="_blank" rel="noopener noreferrer">' + esc(msg.text) + '</a></td>' +
          '<td class="govuk-table__cell">' + esc(msg.user) + '</td>' +
          '<td class="govuk-table__cell govuk-!-white-space-nowrap">' + esc(msg.time) + '</td>' +
          '</tr>';
      });
      return tableWrap(['Workflow', 'Author', 'Time'], rows);
    } else if (task.table_type === 'pr_links') {
      task.messages.forEach(function (msg) {
        rows += '<tr class="govuk-table__row">' +
          '<td class="govuk-table__cell"><a class="govuk-link" href="' + esc(msg.link) + '" target="_blank" rel="noopener noreferrer">' + esc(msg.text) + '</a></td>' +
          '<td class="govuk-table__cell">' + esc(msg.user) + '</td>' +
          '<td class="govuk-table__cell govuk-!-white-space-nowrap">' + esc(msg.time) + '</td>' +
          '</tr>';
      });
      return tableWrap(['PR', 'Posted by', 'Time'], rows);
    } else {
      task.messages.forEach(function (msg) {
        var ackCell = msg.acknowledged_by ? '\uD83D\uDC40 ' + esc(msg.acknowledged_by) : '\u2014';
        rows += '<tr class="govuk-table__row">' +
          '<td class="govuk-table__cell govuk-!-white-space-nowrap">' + esc(msg.user) + '</td>' +
          '<td class="govuk-table__cell"><a class="govuk-link" href="' + esc(msg.link) + '" target="_blank" rel="noopener noreferrer">' + esc(msg.text) + '</a></td>' +
          '<td class="govuk-table__cell govuk-!-white-space-nowrap">' + esc(msg.time) + '</td>' +
          '<td class="govuk-table__cell">' + ackCell + '</td>' +
          '</tr>';
      });
      return tableWrap(['From', 'Message', 'Time', 'Acknowledged by'], rows);
    }
  }

  /* ── Tile / banner helpers ──────────────────────────────────────────────── */
  function countDisplay(status, count) {
    if (status === 'requires_attention') { return String(count); }
    return status === 'ok' ? '\u2713' : '!';
  }

  function statusLabel(status, count) {
    if (status === 'requires_attention') {
      return count + ' item' + (count !== 1 ? 's' : '') + ' to action';
    }
    return status === 'ok' ? 'All clear' : 'Manual check needed';
  }

  function updateLegendText(el, text) {
    if (!el) { return; }
    Array.from(el.childNodes).forEach(function (node) {
      if (node.nodeType === Node.TEXT_NODE) { node.textContent = text; }
    });
  }

  /* ── Sound toggle ───────────────────────────────────────────────────────── */
  var SOUND_KEY = 'mm-sound-enabled';
  var soundToggle = document.getElementById('mm-sound-toggle');
  if (soundToggle) {
    soundToggle.checked = localStorage.getItem(SOUND_KEY) === 'true';
    soundToggle.addEventListener('change', function () {
      localStorage.setItem(SOUND_KEY, soundToggle.checked);
    });
  }

  function playSoundAlert() {
    if (!soundToggle || !soundToggle.checked) { return; }
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      [[440, 0, 0.15], [550, 0.18, 0.15]].forEach(function (note) {
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.value = note[0];
        gain.gain.setValueAtTime(0.25, ctx.currentTime + note[1]);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + note[1] + note[2]);
        osc.start(ctx.currentTime + note[1]);
        osc.stop(ctx.currentTime + note[1] + note[2]);
      });
    } catch (e) { /* AudioContext not available */ }
  }

  var previousTotalCount = parseInt(canvas.dataset.red, 10) || 0;

  /* ── Polling ────────────────────────────────────────────────────────────── */
  function poll() {
    var ts = document.getElementById('mm-last-updated');
    if (ts) { ts.textContent = 'Refreshing\u2026'; }
    fetch(DATA_URL, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (data) {
        var rc = 0, gc = 0, ac = 0;

        data.tasks.forEach(function (task) {
          /* Tile */
          var tile = document.querySelector('[data-task-id="' + task.id + '"]');
          if (tile) {
            tile.className = tile.className.replace(/\bmm-tile--\S+/g, '').trim();
            tile.classList.add('mm-tile--' + task.status);
            var countEl = tile.querySelector('.mm-tile__count');
            var statusEl = tile.querySelector('.mm-tile__status');
            if (countEl) { countEl.textContent = countDisplay(task.status, task.count); }
            if (statusEl) { statusEl.textContent = statusLabel(task.status, task.count); }
          }

          /* Detail card — active messages table */
          var activeContainer = document.getElementById(task.id + '-active-table');
          if (activeContainer) {
            activeContainer.innerHTML = task.messages && task.messages.length ? buildTableHTML(task) : '';
          }

          if (task.status === 'requires_attention') { rc++; }
          else if (task.status === 'ok') { gc++; }
          else { ac++; }
        });

        /* Banner */
        var bannerAction = document.getElementById('mm-banner-action');
        var bannerClear  = document.getElementById('mm-banner-clear');
        var bannerCount  = document.getElementById('mm-banner-count');
        if (bannerAction && bannerClear) {
          if (data.total_count > 0) {
            bannerAction.removeAttribute('hidden');
            bannerClear.setAttribute('hidden', '');
            if (bannerCount) { bannerCount.textContent = data.total_count; }
          } else {
            bannerAction.setAttribute('hidden', '');
            bannerClear.removeAttribute('hidden');
          }
        }

        /* Sound alert if new items have appeared since last poll */
        if (data.total_count > previousTotalCount) { playSoundAlert(); }
        previousTotalCount = data.total_count;

        /* Legend */
        updateLegendText(document.getElementById('mm-legend-red'),   '\u00a0' + rc + ' need action');
        updateLegendText(document.getElementById('mm-legend-green'), '\u00a0' + gc + ' OK');
        updateLegendText(document.getElementById('mm-legend-amber'), '\u00a0' + ac + ' manual check');

        /* Chart */
        if (window._mmChart) {
          window._mmChart.data.datasets[0].data = [rc, gc, ac];
          window._mmChart.update();
        }

        /* Timestamp */
        var ts = document.getElementById('mm-last-updated');
        if (ts && data.fetched_at) { ts.textContent = 'Updated ' + data.fetched_at; }
      })
      .catch(function (err) {
        var ts = document.getElementById('mm-last-updated');
        if (ts) { ts.textContent = 'Refresh failed \u2014 will retry'; }
        console.warn('Milk monitor poll failed:', err);
      });
  }

  setInterval(poll, 60000);
}());
