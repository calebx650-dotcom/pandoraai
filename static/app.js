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
    seg.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const result = btn.dataset.result;
        seg.querySelectorAll('button').forEach((b) => b.classList.remove('active', 'pass', 'fail', 'na'));
        btn.classList.add('active', result);
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

  // ------- Barcode scanner -------
  const bcInput = document.getElementById('barcode-input');
  const bcScan = document.getElementById('barcode-scan');
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
      });
  }
  if (bcInput) {
    bcInput.addEventListener('change', () => lookup(bcInput.value.trim()));
  }
  if (bcScan) {
    bcScan.addEventListener('click', async () => {
      if (!('BarcodeDetector' in window)) {
        if (bcResult) bcResult.textContent = 'Camera scanning not supported on this browser - type the code instead.';
        bcInput && bcInput.focus();
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        const video = document.createElement('video');
        video.srcObject = stream; video.setAttribute('playsinline', ''); video.style.width = '100%';
        video.style.borderRadius = '12px'; video.style.marginTop = '8px';
        bcInput.parentElement.parentElement.appendChild(video);
        await video.play();
        const detector = new BarcodeDetector();
        const tick = async () => {
          try {
            const codes = await detector.detect(video);
            if (codes.length) {
              const code = codes[0].rawValue;
              bcInput.value = code;
              stream.getTracks().forEach(t => t.stop());
              video.remove();
              lookup(code);
              return;
            }
          } catch (e) {}
          requestAnimationFrame(tick);
        };
        tick();
      } catch (e) {
        if (bcResult) bcResult.textContent = 'Camera permission denied.';
      }
    });
  }

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
