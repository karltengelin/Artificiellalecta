(() => {
  const openButton = document.getElementById('open-login');
  const dialog = document.getElementById('login');
  const closeButton = document.getElementById('close-login');
  const password = document.getElementById('password');
  const toggle = document.getElementById('toggle-password');

  function setPasswordVisibility(visible) {
    password.type = visible ? 'text' : 'password';
    toggle.firstChild.textContent = visible ? 'Dölj' : 'Visa';
  }

  if (dialog.hasAttribute('data-open')) {
    dialog.removeAttribute('open');
    dialog.showModal();
  }
  openButton.addEventListener('click', () => dialog.showModal());
  closeButton.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) {
      dialog.close();
    }
  });
  openButton.disabled = false;
  if (password && toggle) {
    toggle.hidden = false;
    toggle.addEventListener('click', () => setPasswordVisibility(password.type === 'password'));
    dialog.addEventListener('close', () => {
      password.value = '';
      setPasswordVisibility(false);
    });
  }
})();

(() => {
  const stage = document.getElementById('stage');
  const bgCanvas = document.getElementById('neural-bg');
  const fgCanvas = document.getElementById('neural-fg');
  const bgCtx = bgCanvas.getContext('2d');
  const fgCtx = fgCanvas.getContext('2d');

  if (!bgCtx || !fgCtx) return;

  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');

  let width = 0;
  let height = 0;
  let dpr = 1;
  let radiusBase = 240;

  // Musinteraktion för mjuk lutning/parallax
  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0 };

  // 3D-noder i kokongen runt centrum
  const NODE_COUNT = 78;
  const nodes = [];
  const edges = [];
  const pulses = [];

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = stage.clientWidth;
    height = stage.clientHeight;

    [bgCanvas, fgCanvas].forEach((c) => {
      c.width = Math.floor(width * dpr);
      c.height = Math.floor(height * dpr);
    });

    bgCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fgCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    radiusBase = Math.min(385, width * 0.32, height * 0.40);
    if (width <= 640) radiusBase = Math.min(255, width * 0.43, height * 0.39);
  }

  // Skapa noder i ett sfäriskt skal (kokong) runt mitten med lätt elliptisk bredd för att rama in logotypen
  function initNetwork() {
    nodes.length = 0;
    edges.length = 0;
    pulses.length = 0;

    // Fibonacci-sfär med lätt organisk spridning ger jämn, vacker kokongfördelning
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < NODE_COUNT; i++) {
      const t = (i + 0.5) / NODE_COUNT;
      const phi = Math.acos(1 - 2 * t);
      const theta = goldenAngle * i + (Math.random() - 0.5) * 0.32;

      // Skaltjocklek: mellan 0.78 och 1.26 av basradien så lagren omsluter loggan
      const radialFactor = 0.80 + Math.random() * 0.46;
      // Lätt bredare längs X-axeln för att snyggt omsluta logotyp + ordmärke
      const x = Math.sin(phi) * Math.cos(theta) * 1.32 * radialFactor;
      const y = Math.cos(phi) * 0.94 * radialFactor;
      const z = Math.sin(phi) * Math.sin(theta) * 1.05 * radialFactor;

      nodes.push({
        id: i,
        bx: x,
        by: y,
        bz: z,
        px: 0,
        py: 0,
        pz: 0,
        sx: 0,
        sy: 0,
        scale: 1,
        phase: Math.random() * Math.PI * 2,
        wobbleSpeed: 0.5 + Math.random() * 0.7,
        wobbleAmp: 0.03 + Math.random() * 0.035,
        baseSize: 2.1 + Math.random() * 2.1,
        energy: 0, // 0..1 glöd när noden tar emot eller skickar en signal
        cooldown: 0,
        neighbors: []
      });
    }

    // Koppla varje nod till sina närmaste grannar i 3D-rymden
    const maxDist = 0.62;
    for (let i = 0; i < nodes.length; i++) {
      const candidates = [];
      for (let j = 0; j < nodes.length; j++) {
        if (i === j) continue;
        const dx = nodes[i].bx - nodes[j].bx;
        const dy = nodes[i].by - nodes[j].by;
        const dz = nodes[i].bz - nodes[j].bz;
        const dist = Math.hypot(dx, dy, dz);
        if (dist < maxDist) {
          candidates.push({ j, dist });
        }
      }
      candidates.sort((a, b) => a.dist - b.dist);
      const linkCount = Math.min(4, candidates.length);
      for (let k = 0; k < linkCount; k++) {
        const j = candidates[k].j;
        if (i < j && !nodes[i].neighbors.includes(j)) {
          nodes[i].neighbors.push(j);
          nodes[j].neighbors.push(i);
          edges.push({ a: i, b: j });
        }
      }
    }

    // Starta ett par inledande signaler direkt
    if (!motionPreference.matches) {
      fireNode(0, 2);
      fireNode(Math.floor(NODE_COUNT / 2), 2);
    }
  }

  function fireNode(nodeIdx, depth = 0, fromIdx = -1) {
    const node = nodes[nodeIdx];
    if (!node) return;
    node.energy = 1;
    node.cooldown = 0.65;

    if (depth > 4 || pulses.length > 75) return;

    // Välj 1–2 grannar att skicka signalen vidare till (ej tillbaka till avsändaren)
    const targets = node.neighbors.filter((n) => n !== fromIdx);
    if (targets.length === 0) return;

    // Blanda och välj 1–2 mål
    const count = targets.length > 1 && Math.random() < 0.48 ? 2 : 1;
    for (let c = 0; c < count; c++) {
      const pick = targets[Math.floor(Math.random() * targets.length)];
      pulses.push({
        from: nodeIdx,
        to: pick,
        progress: 0,
        speed: 0.85 + Math.random() * 0.65, // fortplantningshastighet
        depth
      });
    }
  }

  // 3D-rotation runt Y och lätt X-lutning
  function projectNodes(time, rotY, rotX) {
    const cosY = Math.cos(rotY);
    const sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX);
    const sinX = Math.sin(rotX);

    const cx = width * 0.5;
    const cy = height * 0.5;
    const fov = radiusBase * 3.4;

    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      // Organisk "andning" i lokal position
      const wobble = Math.sin(time * n.wobbleSpeed + n.phase) * n.wobbleAmp;
      const lx = (n.bx + wobble * n.bx) * radiusBase;
      const ly = (n.by + Math.cos(time * n.wobbleSpeed * 0.8 + n.phase) * n.wobbleAmp) * radiusBase;
      const lz = (n.bz + wobble * n.bz) * radiusBase;

      // Rotera kring Y
      const x1 = lx * cosY - lz * sinY;
      const z1 = lx * sinY + lz * cosY;

      // Rotera kring X
      const y2 = ly * cosX - z1 * sinX;
      const z2 = ly * sinX + z1 * cosX;

      const perspective = fov / (fov - z2);
      n.px = x1;
      n.py = y2;
      n.pz = z2;
      n.scale = perspective;
      n.sx = cx + x1 * perspective;
      n.sy = cy + y2 * perspective;

      // Mjuk avklingning av nodens glöd
      if (n.energy > 0) {
        n.energy = Math.max(0, n.energy - 0.022);
      }
      if (n.cooldown > 0) {
        n.cooldown = Math.max(0, n.cooldown - 0.016);
      }
    }
  }

  function drawLayer(ctx, isForeground) {
    ctx.clearRect(0, 0, width, height);

    // 1. Rita synapser (streck mellan noder)
    ctx.lineCap = 'round';
    for (let i = 0; i < edges.length; i++) {
      const e = edges[i];
      const a = nodes[e.a];
      const b = nodes[e.b];
      const avgZ = (a.pz + b.pz) * 0.5;

      if ((isForeground && avgZ < 0) || (!isForeground && avgZ >= 0)) continue;

      // Djup-opacitet
      const depthNorm = Math.max(0, Math.min(1, (avgZ + radiusBase * 1.2) / (radiusBase * 2.4)));
      const alpha = 0.11 + depthNorm * 0.24;

      ctx.strokeStyle = `rgba(169, 145, 242, ${alpha.toFixed(3)})`;
      ctx.lineWidth = (0.7 + depthNorm * 0.75);
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();
    }

    // 2. Rita fortplantande neuron-signaler längs strecken
    for (let i = 0; i < pulses.length; i++) {
      const p = pulses[i];
      const a = nodes[p.from];
      const b = nodes[p.to];
      const avgZ = (a.pz + b.pz) * 0.5;

      if ((isForeground && avgZ < 0) || (!isForeground && avgZ >= 0)) continue;

      const head = p.progress;              // 0 -> 1
      const tail = Math.max(0, head - 0.55); // ljusvågens svans
      const fadeOut = head > 0.85 ? (1 - head) / 0.15 : 1;
      const intensity = Math.max(0.15, fadeOut);

      // Gradient längs synapsen: lyser upp vid källänden först och fortplantar sig mot målnoden
      const grad = ctx.createLinearGradient(a.sx, a.sy, b.sx, b.sy);
      const stopTail = Math.max(0, Math.min(1, tail));
      const stopBody = Math.max(0, Math.min(1, head - 0.12));
      const stopHead = Math.max(0, Math.min(1, head));
      const stopAfter = Math.min(1, stopHead + 0.03);

      grad.addColorStop(0, 'rgba(105, 81, 207, 0)');
      if (stopTail > 0) {
        grad.addColorStop(stopTail, 'rgba(105, 81, 207, 0)');
      }
      if (stopBody > stopTail) {
        grad.addColorStop(stopBody, `rgba(169, 145, 242, ${(0.85 * intensity).toFixed(3)})`);
      }
      grad.addColorStop(stopHead, `rgba(244, 242, 255, ${(1.0 * intensity).toFixed(3)})`);
      if (stopAfter < 1) {
        grad.addColorStop(stopAfter, 'rgba(169, 145, 242, 0)');
      }
      grad.addColorStop(1, 'rgba(169, 145, 242, 0)');

      // Yttre mjuk lila glöd längs vågen
      ctx.save();
      ctx.strokeStyle = grad;
      ctx.lineWidth = 4.2 * ((a.scale + b.scale) * 0.5);
      ctx.globalAlpha = 0.42;
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();

      // Skarp lysande kärna
      ctx.globalAlpha = 1;
      ctx.lineWidth = 1.9 * ((a.scale + b.scale) * 0.5);
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();

      // Lysande spetspunkt där impulsen just nu befinner sig
      const hx = a.sx + (b.sx - a.sx) * head;
      const hy = a.sy + (b.sy - a.sy) * head;
      const headRadius = 3.2 * ((a.scale + b.scale) * 0.5);
      const dotGrad = ctx.createRadialGradient(hx, hy, 0, hx, hy, headRadius * 3.2);
      dotGrad.addColorStop(0, `rgba(255, 255, 255, ${(0.95 * intensity).toFixed(3)})`);
      dotGrad.addColorStop(0.4, `rgba(210, 197, 255, ${(0.65 * intensity).toFixed(3)})`);
      dotGrad.addColorStop(1, 'rgba(105, 81, 207, 0)');
      ctx.fillStyle = dotGrad;
      ctx.beginPath();
      ctx.arc(hx, hy, headRadius * 3.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // 3. Rita noder (sorterade efter djup för ren z-ordning)
    const layerNodes = nodes
      .filter((n) => (isForeground ? n.pz >= 0 : n.pz < 0))
      .sort((a, b) => a.pz - b.pz);

    for (let i = 0; i < layerNodes.length; i++) {
      const n = layerNodes[i];
      const depthNorm = Math.max(0, Math.min(1, (n.pz + radiusBase * 1.2) / (radiusBase * 2.4)));
      const r = n.baseSize * n.scale * (1 + n.energy * 0.65);

      // Glödande aura när noden är aktiv
      const glowRadius = r * (3.0 + n.energy * 3.8);
      const aura = ctx.createRadialGradient(n.sx, n.sy, 0, n.sx, n.sy, glowRadius);
      const auraAlpha = (0.18 + depthNorm * 0.22 + n.energy * 0.55);
      aura.addColorStop(0, `rgba(210, 197, 255, ${auraAlpha.toFixed(3)})`);
      aura.addColorStop(0.5, `rgba(105, 81, 207, ${(auraAlpha * 0.5).toFixed(3)})`);
      aura.addColorStop(1, 'rgba(105, 81, 207, 0)');

      ctx.fillStyle = aura;
      ctx.beginPath();
      ctx.arc(n.sx, n.sy, glowRadius, 0, Math.PI * 2);
      ctx.fill();

      // Nodens kärna
      const coreAlpha = (0.45 + depthNorm * 0.45 + n.energy * 0.2);
      ctx.fillStyle = n.energy > 0.35
        ? `rgba(244, 242, 255, ${Math.min(1, coreAlpha).toFixed(3)})`
        : `rgba(169, 145, 242, ${Math.min(1, coreAlpha).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  let lastTime = performance.now();
  let rotY = 0.32;
  let animationFrame = 0;
  let autoPulseTimer = 0;

  function tick(now) {
    const dt = Math.min(0.05, (now - lastTime) / 1000);
    lastTime = now;
    const timeSec = now / 1000;

    // Mjuk musföljning
    pointer.x += (pointer.targetX - pointer.x) * 0.05;
    pointer.y += (pointer.targetY - pointer.y) * 0.05;

    rotY += dt * (0.12 + pointer.x * 0.12);
    const rotX = 0.24 + Math.sin(timeSec * 0.25) * 0.10 + pointer.y * 0.13;

    // Uppdatera aktiva signaler
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.progress += dt * p.speed;
      if (p.progress >= 1) {
        const targetNode = nodes[p.to];
        if (targetNode && targetNode.cooldown <= 0) {
          fireNode(p.to, p.depth + 1, p.from);
        } else if (targetNode) {
          targetNode.energy = Math.max(targetNode.energy, 0.75);
        }
        pulses.splice(i, 1);
      }
    }

    // Skicka nya spontana impulser i nätverket med jämna mellanrum
    autoPulseTimer += dt;
    if (autoPulseTimer > 0.72) {
      autoPulseTimer = 0;
      if (pulses.length < 14) {
        const randomIdx = Math.floor(Math.random() * nodes.length);
        if (nodes[randomIdx].cooldown <= 0) {
          fireNode(randomIdx, 0);
        }
      }
    }

    projectNodes(timeSec, rotY, rotX);
    drawLayer(bgCtx, false);
    drawLayer(fgCtx, true);

    animationFrame = requestAnimationFrame(tick);
  }

  function redraw() {
    resize();
    if (motionPreference.matches) {
      projectNodes(0, 0.32, 0.24);
      drawLayer(bgCtx, false);
      drawLayer(fgCtx, true);
    }
  }

  function updateMotion() {
    cancelAnimationFrame(animationFrame);
    initNetwork();
    redraw();
    if (!motionPreference.matches) {
      lastTime = performance.now();
      animationFrame = requestAnimationFrame(tick);
    }
  }

  stage.addEventListener('pointermove', (event) => {
    if (!motionPreference.matches && event.pointerType === 'mouse') {
      pointer.targetX = (event.clientX / width - 0.5) * 2;
      pointer.targetY = (event.clientY / height - 0.5) * 2;
    }
  });

  stage.addEventListener('pointerleave', () => {
    pointer.targetX = 0;
    pointer.targetY = 0;
  });

  new ResizeObserver(redraw).observe(stage);
  motionPreference.addEventListener('change', updateMotion);
  updateMotion();
})();
