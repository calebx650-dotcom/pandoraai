// IGH fireNspec - client behaviors

(function () {
  // ------- connection indicator -------
  const conn = document.querySelector('.topbar .conn');
  function updateConn() {
    if (!conn) return;
    if (navigator.onLine) {
      conn.classList.remove('offline');
      const t = conn.querySelector('.txt'); if (t) t.textContent = 'Online';
    } else {
      conn.classList.add('offline');
      const t = conn.querySelector('.txt'); if (t) t.textContent = 'Offline';
    }
  }
  window.addEventListener('online', updateConn);
  window.addEventListener('offline', updateConn);
  updateConn();

  // ------- service worker -------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
  }

  // ------- segmented Pass/Fail/NA -------
  document.querySelectorAll('.seg').forEach((seg) => {
    const itemId = seg.dataset.itemId;
    const inspectionId = seg.dataset.inspectionId;
    const defBtn = seg.closest('.item') && seg.closest('.item').querySelector('.deficiency-btn');
    seg.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const result = btn.dataset.result;
        seg.querySelectorAll('button').forEach((b) => b.classList.remove('active', 'pass', 'fail', 'na'));
        btn.classList.add('active', result);
        if (defBtn) defBtn.style.display = result === 'fail' ? 'block' : 'none';
        autosave(inspectionId, itemId, { result });
      });
    });
  });

  document.querySelectorAll('[data-autosave-note]').forEach((input) => {
    let timer;
    input.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => autosave(input.dataset.inspectionId, input.dataset.itemId, { note: input.value }), 500);
    });
  });

  document.querySelectorAll('[data-autosave-value]').forEach((input) => {
    let timer;
    input.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => autosave(input.dataset.inspectionId, input.dataset.itemId, { result: input.value }), 500);
    });
  });

  function autosave(inspectionId, itemId, payload) {
    const banner = document.getElementById('save-banner');
    if (banner) banner.textContent = 'Saving...';
    const body = new URLSearchParams({ item_id: itemId, ...payload });
    fetch(`/inspections/${inspectionId}/save`, {
      method: 'POST', body, headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(r => r.json()).then(() => {
      if (banner) {
        banner.textContent = 'Saved';
        setTimeout(() => { if (banner.textContent === 'Saved') banner.textContent = ''; }, 1200);
      }
    }).catch(() => { if (banner) banner.textContent = 'Offline - will retry'; });
  }

  // ------- GPS capture -------
  const gpsBtn = document.getElementById('gps-btn');
  if (gpsBtn) {
    gpsBtn.addEventListener('click', () => {
      if (!navigator.geolocation) { alert('Geolocation not available.'); return; }
      gpsBtn.textContent = 'Locating...';
      navigator.geolocation.getCurrentPosition(
        (p) => {
          document.getElementById('gps_lat').value = p.coords.latitude.toFixed(6);
          document.getElementById('gps_lng').value = p.coords.longitude.toFixed(6);
          gpsBtn.textContent = `Captured ${p.coords.latitude.toFixed(4)}, ${p.coords.longitude.toFixed(4)}`;
        },
        () => { gpsBtn.textContent = 'Tap to retry'; }
      );
    });
  }

  // Capture GPS automatically on firewatch round form
  if (document.getElementById('round_gps_lat') && navigator.geolocation) {
    navigator.geolocation.getCurrentPosition((p) => {
      document.getElementById('round_gps_lat').value = p.coords.latitude.toFixed(6);
      document.getElementById('round_gps_lng').value = p.coords.longitude.toFixed(6);
    }, () => {});
  }

  // ------- Barcode / QR scanner -------
  // Two paths:
  //   1) Manual entry in #barcode-input  -> lookup() + show match inline
  //   2) Tap any [data-scan-trigger]      -> open full-screen camera modal
  //      modes: "lookup" (fills #barcode-input + calls /api/lookup_barcode)
  //             "navigate" (extracts device id/code -> redirects to its record)
  const bcInput = document.getElementById('barcode-input');
  const bcResult = document.getElementById('barcode-result');

  function lookup(code) {
    if (!code) return;
    fetch('/api/lookup_barcode?code=' + encodeURIComponent(code))
      .then(r => r.json())
      .then(j => {
        if (!bcResult) return;
        if (j.ok) {
          const d = j.device;
          bcResult.style.color = 'var(--pass)';
          bcResult.innerHTML = `Match: <strong>${d.model || d.device_type}</strong> at ${d.location || '-'} (${d.customer_name})`;
        } else {
          bcResult.style.color = 'var(--fail)';
          bcResult.textContent = 'No device with that code on file.';
        }
      })
      .catch(() => {
        if (bcResult) {
          bcResult.style.color = 'var(--fail)';
          bcResult.textContent = 'Lookup failed - check your connection.';
        }
      });
  }
  if (bcInput) {
    bcInput.addEventListener('change', () => lookup(bcInput.value.trim()));
  }

  // ---- Scanner modal ----
  const modal = document.getElementById('scanner-modal');
  const statusEl = document.getElementById('scanner-status');
  const readerId = 'scanner-reader';
  let html5Qrcode = null;        // html5-qrcode instance (lazy-init)
  let scannerLoaded = false;     // script tag injected?
  let onSuccessCb = null;        // current mode's handler

  function setStatus(msg, tone) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.classList.remove('ok', 'err');
    if (tone === 'ok') statusEl.classList.add('ok');
    if (tone === 'err') statusEl.classList.add('err');
  }

  function loadScannerScript() {
    if (scannerLoaded) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
      s.async = true;
      s.onload = () => { scannerLoaded = true; resolve(); };
      s.onerror = () => reject(new Error('Could not load scanner script'));
      document.head.appendChild(s);
    });
  }

  async function openScanner(mode) {
    if (!modal) return;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    setStatus('Requesting camera access...');

    try {
      await loadScannerScript();
    } catch (e) {
      setStatus('Could not load the scanner. Check your connection.', 'err');
      return;
    }
    if (!window.Html5Qrcode) {
      setStatus('Scanner unavailable on this browser.', 'err');
      return;
    }

    onSuccessCb = (decoded) => handleScan(decoded, mode);

    try {
      html5Qrcode = new Html5Qrcode(readerId, { verbose: false });
      const config = {
        fps: 10,
        qrbox: (vw, vh) => {
          const min = Math.min(vw, vh);
          const size = Math.floor(min * 0.7);
          return { width: size, height: size };
        },
        aspectRatio: 1.0,
        // Use camera default formats; html5-qrcode supports QR + common 1D barcodes.
        showTorchButtonIfSupported: true,
      };
      await html5Qrcode.start(
        { facingMode: 'environment' },
        config,
        (decodedText) => {
          if (onSuccessCb) {
            const cb = onSuccessCb;
            onSuccessCb = null; // one-shot
            cb(decodedText);
          }
        },
        () => { /* per-frame "not found" callback — ignore */ }
      );
      setStatus('Point camera at a QR code or barcode');
    } catch (err) {
      console.error(err);
      setStatus('Camera permission denied or no camera available.', 'err');
    }
  }

  async function closeScanner() {
    if (!modal) return;
    if (html5Qrcode) {
      try { await html5Qrcode.stop(); } catch (e) {}
      try { html5Qrcode.clear(); } catch (e) {}
      html5Qrcode = null;
    }
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    onSuccessCb = null;
  }

  function extractDeviceCode(decoded) {
    // Decoded text may be a full URL ( /d/123 or /qr/<token> ) or a raw barcode.
    // Return { kind, value } so the caller can route appropriately.
    if (!decoded) return null;
    try {
      const u = new URL(decoded);
      // Same-origin URLs we generated ourselves: /d/<id> or /qr/<token>
      const m1 = u.pathname.match(/^\/d\/(\d+)\/?$/);
      if (m1) return { kind: 'device_id', value: m1[1], url: u.href };
      const m2 = u.pathname.match(/^\/qr\/([^/]+)\/?$/);
      if (m2) return { kind: 'qr_token', value: m2[1], url: u.href };
      const m3 = u.pathname.match(/^\/devices\/(\d+)/);
      if (m3) return { kind: 'device_id', value: m3[1], url: u.href };
      // Foreign URL — treat the whole string as a barcode value
      return { kind: 'barcode', value: decoded };
    } catch (e) {
      // Not a URL — raw barcode/serial string
      return { kind: 'barcode', value: decoded.trim() };
    }
  }

  function handleScan(decoded, mode) {
    const parsed = extractDeviceCode(decoded);
    if (!parsed) {
      setStatus('Could not read that code. Try again.', 'err');
      onSuccessCb = (d) => handleScan(d, mode); // rearm
      return;
    }

    if (mode === 'navigate') {
      // Direct redirect — works for our own QR codes (URL) and raw barcodes.
      setStatus('Found - opening device...', 'ok');
      if (parsed.kind === 'device_id') {
        window.location.href = '/devices/' + parsed.value;
      } else if (parsed.kind === 'qr_token') {
        window.location.href = '/qr/' + parsed.value;
      } else {
        // Raw barcode — look it up first to resolve to a device id.
        fetch('/api/lookup_barcode?code=' + encodeURIComponent(parsed.value))
          .then(r => r.json())
          .then(j => {
            if (j.ok && j.device && j.device.id) {
              window.location.href = '/devices/' + j.device.id;
            } else {
              setStatus('No device matches "' + parsed.value + '".', 'err');
              onSuccessCb = (d) => handleScan(d, mode);
            }
          })
          .catch(() => {
            setStatus('Lookup failed - check your connection.', 'err');
            onSuccessCb = (d) => handleScan(d, mode);
          });
      }
      return;
    }

    // mode === 'lookup' — fill the inspection's barcode field and resolve.
    let code = parsed.value;
    if (parsed.kind === 'device_id') {
      // We scanned our own /d/<id> QR. Resolve to the device's barcode for the
      // input + highlight, but also let lookup() show the human-readable match.
      setStatus('Found device - loading details...', 'ok');
      fetch('/api/devices/' + parsed.value + '/summary')
        .then(r => r.ok ? r.json() : null)
        .then(j => {
          if (j && j.barcode && bcInput) {
            bcInput.value = j.barcode;
            lookup(j.barcode);
          } else if (bcInput) {
            // Fall back to the URL string — at least the inspector sees something.
            bcInput.value = decoded;
            lookup(decoded);
          }
          closeScanner();
        })
        .catch(() => {
          if (bcInput) { bcInput.value = decoded; lookup(decoded); }
          closeScanner();
        });
      return;
    }
    if (parsed.kind === 'qr_token') {
      // Not super useful in lookup mode — just close + open the device page.
      setStatus('Opening device...', 'ok');
      window.location.href = '/qr/' + parsed.value;
      return;
    }
    // Raw barcode
    if (bcInput) bcInput.value = code;
    setStatus('Got "' + code + '"', 'ok');
    lookup(code);
    setTimeout(closeScanner, 350);
  }

  // Wire every scan trigger on the page.
  document.querySelectorAll('[data-scan-trigger]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const mode = btn.dataset.scanMode || 'lookup';
      openScanner(mode);
    });
  });

  // Close handlers (backdrop, X button, ESC key)
  document.querySelectorAll('[data-scanner-close]').forEach((el) => {
    el.addEventListener('click', closeScanner);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal && modal.classList.contains('open')) {
      closeScanner();
    }
  });

  // ------- Signature pads -------
  document.querySelectorAll('.sig-pad-wrap').forEach(setupSigPad);
  function setupSigPad(wrap) {
    const canvas = wrap.querySelector('.sig-pad');
    const clearBtn = wrap.querySelector('.sig-clear');
    const status = wrap.querySelector('.sig-status');
    const hidden = wrap.querySelector('.sig-data');
    const inspectionId = wrap.dataset.inspectionId;
    const who = wrap.dataset.who;
    const ctx = canvas.getContext('2d');
    function fit() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.strokeStyle = '#13334A';
    }
    fit(); window.addEventListener('resize', fit);

    let drawing = false, last = null, dirty = false;
    function pos(e) {
      const r = canvas.getBoundingClientRect();
      const t = e.touches ? e.touches[0] : e;
      return { x: t.clientX - r.left, y: t.clientY - r.top };
    }
    function down(e) { e.preventDefault(); drawing = true; last = pos(e); }
    function move(e) {
      if (!drawing) return; e.preventDefault();
      const p = pos(e);
      ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke();
      last = p; dirty = true;
    }
    function up() {
      if (!drawing) return;
      drawing = false;
      const data = canvas.toDataURL('image/png');
      hidden.value = data;
      if (status) status.textContent = 'Saved';
      fetch(`/inspections/${inspectionId}/signature`, {
        method: 'POST',
        body: new URLSearchParams({ who, data_url: data }),
      }).catch(() => {});
    }
    canvas.addEventListener('mousedown', down);
    canvas.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    canvas.addEventListener('touchstart', down, { passive: false });
    canvas.addEventListener('touchmove', move, { passive: false });
    canvas.addEventListener('touchend', up);
    clearBtn.addEventListener('click', () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      hidden.value = ''; dirty = false;
      if (status) status.textContent = '';
    });
  }
})();
