"use strict";
(() => {
  const TOKEN = JSON.parse(document.getElementById("editor-config").textContent).token;
  const $ = id => document.getElementById(id);
  const encoder = new TextEncoder();
  const compact = p => JSON.stringify(p);
  const copy = p => structuredClone(p);
  const rgb565 = (r, g, b) => ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
  const rgb = n => [Math.round(((n >> 11) & 31) * 255 / 31), Math.round(((n >> 5) & 63) * 255 / 63), Math.round((n & 31) * 255 / 31)];
  const hex = n => "#" + rgb(n).map(v => v.toString(16).padStart(2, "0")).join("");
  const fromHex = text => rgb565(...[1, 3, 5].map(i => parseInt(text.slice(i, i + 2), 16)));
  const bytesTo64 = bytes => btoa(String.fromCharCode(...bytes));
  const byte64 = data => Uint8Array.from(atob(data), c => c.charCodeAt(0));
  const validId = id => typeof id === "string" && /^[A-Za-z][A-Za-z0-9_]{0,23}$/.test(id);
  const integer = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
  const sameKeys = (o, keys) => o && typeof o === "object" && !Array.isArray(o) && Object.keys(o).length === keys.length && keys.every(k => Object.hasOwn(o, k));
  const assert = (yes, message) => { if (!yes) throw new Error(message); };
  function textValid(text) {
    return typeof text === "string" && encoder.encode(text).length >= 1 && encoder.encode(text).length <= 192 &&
      !/[\u0000-\u0009\u000b-\u001f\u007f-\u009f\ud800-\udfff]/u.test(text);
  }
  function validate(p) {
    assert(sameKeys(p, ["schema_version", "width", "height", "pages", "images"]) && p.schema_version === 1, "页面包字段或 schema_version 不正确。");
    assert(integer(p.width, 1, 320) && integer(p.height, 1, 320), "画布每边必须为 1～320 像素。");
    assert(Array.isArray(p.pages) && p.pages.length >= 1 && p.pages.length <= 4, "页面数量必须为 1～4。");
    assert(Array.isArray(p.images) && p.images.length <= 4, "最多保存 4 张小图标。");
    const images = new Map(); let totalPixels = 0;
    for (const image of p.images) {
      assert(sameKeys(image, ["id", "width", "height", "data"]) && validId(image.id) && !images.has(image.id), "图标 ID 或字段不正确、重复。");
      assert(integer(image.width, 1, 48) && integer(image.height, 1, 48), "图标每边必须为 1～48 像素。");
      assert(typeof image.data === "string" && image.data.length % 4 === 0 && /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(image.data), "图标必须是标准 base64 RGB565 数据。");
      const decoded = byte64(image.data);
      assert(bytesTo64(decoded) === image.data && decoded.length === image.width * image.height * 2, "图标像素长度或 base64 填充不正确。");
      totalPixels += decoded.length; images.set(image.id, image);
    }
    assert(totalPixels <= 4608, "所有图标的 RGB565 数据合计不能超过 4608 字节。");
    const pages = new Set(); let count = 0;
    const point = (x, y) => integer(x, 0, p.width - 1) && integer(y, 0, p.height - 1);
    for (const page of p.pages) {
      assert(sameKeys(page, ["id", "background", "widgets"]) && validId(page.id) && !pages.has(page.id), "页面 ID 或字段不正确、重复。");
      pages.add(page.id);
      assert(integer(page.background, 0, 65535) && Array.isArray(page.widgets), "背景色或组件列表不正确。");
      const ids = new Set();
      for (const w of page.widgets) {
        assert(validId(w.id) && !ids.has(w.id), "同一页的组件 ID 不正确或重复。"); ids.add(w.id); count++;
        if (w.type === "text") {
          assert(sameKeys(w, ["id", "type", "x", "y", "text", "color"]) && point(w.x, w.y) && textValid(w.text) && integer(w.color, 0, 65535), `文字组件 ${w.id} 的坐标、颜色或文字不正确。`);
        } else if (w.type === "rect") {
          assert(sameKeys(w, ["id", "type", "x", "y", "width", "height", "color", "filled"]) && point(w.x, w.y) && integer(w.width, 1, p.width - w.x) && integer(w.height, 1, p.height - w.y) && integer(w.color, 0, 65535) && typeof w.filled === "boolean", `矩形 ${w.id} 必须完整位于画布内。`);
        } else if (w.type === "line") {
          assert(sameKeys(w, ["id", "type", "x0", "y0", "x1", "y1", "color"]) && point(w.x0, w.y0) && point(w.x1, w.y1) && integer(w.color, 0, 65535), `线段 ${w.id} 的端点必须在画布内。`);
        } else if (w.type === "image") {
          const image = images.get(w.asset);
          assert(sameKeys(w, ["id", "type", "x", "y", "asset"]) && image && point(w.x, w.y) && w.x + image.width <= p.width && w.y + image.height <= p.height, `图标 ${w.id} 引用缺失或超出画布。`);
        } else throw new Error("未知组件类型：" + String(w.type));
      }
    }
    assert(count <= 32, "全部页面的组件合计最多 32 个。");
    assert(encoder.encode(compact(p)).length <= 8192, "页面包超过 8192 字节，请减少图标大小或组件数量。");
    return p;
  }
  function smile() {
    const bytes = [];
    for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
      const eye = y >= 4 && y <= 6 && ((x >= 4 && x <= 5) || (x >= 10 && x <= 11));
      const mouth = (y === 11 && x >= 5 && x <= 10) || (y === 10 && (x === 4 || x === 11));
      const c = eye || mouth ? rgb565(12, 36, 42) : rgb565(244, 193, 64);
      bytes.push(c >> 8, c & 255);
    }
    return {id: "smile", width: 16, height: 16, data: bytesTo64(bytes)};
  }
  let project = {schema_version: 1, width: 160, height: 128, pages: [
    {id: "home", background: rgb565(12, 27, 38), widgets: [
      {id: "title", type: "text", x: 10, y: 12, text: "AI 小创客", color: rgb565(98, 224, 210)},
      {id: "face", type: "image", x: 132, y: 12, asset: "smile"},
      {id: "subtitle", type: "text", x: 10, y: 38, text: "你好，创客！", color: 65535},
      {id: "card", type: "rect", x: 10, y: 66, width: 140, height: 36, color: rgb565(17, 88, 89), filled: true},
      {id: "status", type: "text", x: 20, y: 78, text: "准备就绪", color: 65535},
      {id: "rule", type: "line", x0: 10, y0: 115, x1: 149, y1: 115, color: rgb565(83, 110, 124)}]},
    {id: "status", background: rgb565(10, 30, 37), widgets: [
      {id: "heading", type: "text", x: 10, y: 12, text: "机器人状态", color: rgb565(98, 224, 210)},
      {id: "value", type: "text", x: 10, y: 42, text: "温度：25 度", color: 65535},
      {id: "bar", type: "rect", x: 10, y: 78, width: 100, height: 12, color: rgb565(67, 188, 147), filled: true}]}], images: [smile()]};
  let pageIndex = 0, selected = "title", device = null, dragging = null;
  const page = () => project.pages[pageIndex];
  const widget = () => page().widgets.find(w => w.id === selected);
  const notice = (message, mode = "") => { $("message").textContent = message; $("message").className = "message " + mode; };
  const setProject = p => { project = copy(validate(p)); pageIndex = 0; selected = null; render(); };
  const transact = fn => { const previous = copy(project); try { fn(); validate(project); render(); } catch (error) { project = previous; render(); throw error; } };
  function uniqueId(prefix, values) { let i = 1; while (values.includes(prefix + i)) i++; return prefix + i; }
  function imageCanvas(image) {
    const out = document.createElement("canvas"); out.width = image.width; out.height = image.height;
    const ctx = out.getContext("2d"), pixels = ctx.createImageData(image.width, image.height), bytes = byte64(image.data);
    for (let i = 0; i < bytes.length; i += 2) { const c = rgb(bytes[i] * 256 + bytes[i + 1]); pixels.data.set([...c, 255], i * 2); }
    ctx.putImageData(pixels, 0, 0); return out;
  }
  function bounds(w) {
    if (w.type === "line") return {x: Math.min(w.x0, w.x1), y: Math.min(w.y0, w.y1), width: Math.abs(w.x1 - w.x0) + 1, height: Math.max(5, Math.abs(w.y1 - w.y0) + 1)};
    if (w.type === "image") { const a = project.images.find(a => a.id === w.asset); return {x: w.x, y: w.y, width: a.width, height: a.height}; }
    if (w.type === "rect") return w;
    const lines = w.text.split("\n");
    return {x: w.x, y: w.y, width: Math.max(6, ...lines.map(s => [...s].reduce((n, c) => n + (c.codePointAt(0) > 127 ? 12 : 7), 0))), height: lines.length * 16};
  }
  function draw() {
    const canvas = $("preview"); canvas.width = project.width; canvas.height = project.height;
    const scale = Math.min(3, 480 / project.width, 420 / project.height);
    canvas.style.width = project.width * scale + "px"; canvas.style.height = project.height * scale + "px";
    const ctx = canvas.getContext("2d"); ctx.imageSmoothingEnabled = false; ctx.fillStyle = hex(page().background); ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (const w of page().widgets) {
      ctx.fillStyle = ctx.strokeStyle = hex(w.color || 0); ctx.lineWidth = 1;
      if (w.type === "text") { ctx.font = '12px "Microsoft YaHei",sans-serif'; ctx.textBaseline = "alphabetic"; w.text.split("\n").forEach((s, i) => ctx.fillText(s, w.x, w.y + 12 + i * 16)); }
      if (w.type === "rect") { if (w.filled) ctx.fillRect(w.x, w.y, w.width, w.height); else ctx.strokeRect(w.x + .5, w.y + .5, w.width - 1, w.height - 1); }
      if (w.type === "line") { ctx.beginPath(); ctx.moveTo(w.x0 + .5, w.y0 + .5); ctx.lineTo(w.x1 + .5, w.y1 + .5); ctx.stroke(); }
      if (w.type === "image") ctx.drawImage(imageCanvas(project.images.find(i => i.id === w.asset)), w.x, w.y);
    }
    const w = widget();
    if (w) { const b = bounds(w); ctx.strokeStyle = "#8af0eb"; ctx.setLineDash([2, 2]); ctx.strokeRect(b.x - .5, b.y - .5, b.width + 1, b.height + 1); }
  }
  const names = {text: "文字", rect: "矩形", line: "线段", image: "图标"};
  function renderLists() {
    $("page-list").replaceChildren(...project.pages.map((p, i) => {
      const b = document.createElement("button"); b.className = "page-item" + (i === pageIndex ? " active" : "");
      const label = document.createElement("span"); label.textContent = p.id;
      const count = document.createElement("small"); count.textContent = p.widgets.length + " 项";
      b.append(label, count); b.onclick = () => { pageIndex = i; selected = null; render(); }; return b;
    }));
    $("layer-list").replaceChildren(...[...page().widgets].reverse().map(w => {
      const b = document.createElement("button"); b.className = "layer-item" + (selected === w.id ? " active" : "");
      const label = document.createElement("span"); label.textContent = w.id;
      const type = document.createElement("small"); type.textContent = names[w.type]; b.append(label, type);
      b.onclick = () => { selected = w.id; render(); }; return b;
    }));
    $("asset-list").replaceChildren(...project.images.map(a => {
      const row = document.createElement("div"); row.className = "asset-row";
      const text = document.createElement("span"); text.textContent = `${a.id} · ${a.width}×${a.height}`;
      const button = document.createElement("button"); button.textContent = "删除"; button.title = "删除素材及全部引用";
      button.onclick = () => { transact(() => { project.images = project.images.filter(i => i.id !== a.id); for (const p of project.pages) p.widgets = p.widgets.filter(w => w.type !== "image" || w.asset !== a.id); }); };
      row.append(imageCanvas(a), text, button); return row;
    }));
  }
  function field(label, key, type, value, onChange, options) {
    const wrap = document.createElement("div"); wrap.className = "field";
    const lab = document.createElement("label"); lab.textContent = label; lab.htmlFor = "prop-" + key;
    let input;
    if (type === "select") { input = document.createElement("select"); options.forEach(option => { const o = document.createElement("option"); o.value = option; o.textContent = option; input.append(o); }); }
    else if (type === "textarea") input = document.createElement("textarea");
    else { input = document.createElement("input"); input.type = type; if (type === "number") input.step = "1"; }
    input.id = "prop-" + key;
    if (key === "id") input.title = "英文字母开头，仅含字母、数字、下划线，最长24字符";
    if (type === "checkbox") input.checked = value; else input.value = value;
    input.addEventListener("change", () => { try { onChange(type === "checkbox" ? input.checked : type === "number" ? Number(input.value) : input.value); notice("组件已更新，尚未写入开发板。"); } catch (e) { notice(e.message, "error"); renderProperties(); } });
    wrap.append(lab, input); return wrap;
  }
  function renderProperties() {
    const w = widget(), out = $("properties"); out.replaceChildren(); $("component-actions").hidden = !w;
    if (!w) { const p = document.createElement("p"); p.className = "help"; p.textContent = "选择画布或图层中的组件进行编辑。"; out.append(p); return; }
    const set = (key, value) => transact(() => { const target = widget(); target[key] = value; if (key === "id") selected = value; });
    out.append(field("组件 ID", "id", "text", w.id, value => set("id", value)));
    const coords = w.type === "line" ? ["x0", "y0", "x1", "y1"] : w.type === "rect" ? ["x", "y", "width", "height"] : ["x", "y"];
    const grid = document.createElement("div"); grid.className = "field-grid";
    coords.forEach(key => grid.append(field(({width: "宽度", height: "高度"})[key] || key.toUpperCase(), key, "number", w[key], value => set(key, value)))); out.append(grid);
    if (w.type === "text") out.append(field("文字内容 · 12px / 换行16px", "text", "textarea", w.text, value => set("text", value)));
    if (Object.hasOwn(w, "color")) out.append(field("颜色", "color", "color", hex(w.color), value => set("color", fromHex(value))));
    if (w.type === "rect") out.append(field("填充矩形", "filled", "checkbox", w.filled, value => set("filled", value)));
    if (w.type === "image") out.append(field("图标素材", "asset", "select", w.asset, value => set("asset", value), project.images.map(i => i.id)));
  }
  function render() {
    if (!project.pages[pageIndex]) pageIndex = 0;
    if (!widget()) selected = null;
    renderLists(); renderProperties(); draw();
    $("page-id").value = page().id; $("background").value = hex(page().background);
    const size = `${project.width}x${project.height}`; $("canvas-size").value = size;
    $("canvas-caption").textContent = `${project.width} × ${project.height} · RGB565`;
    const bytes = encoder.encode(compact(project)).length;
    $("size-badge").textContent = `${bytes} / 8192 字节`; $("size-badge").className = bytes > 8192 ? "over" : "";
  }
  function add(type) {
    transact(() => {
      const id = uniqueId(type, page().widgets.map(w => w.id));
      const item = type === "text" ? {id, type, x: 8, y: 8, text: "新的文字", color: 65535} : type === "rect" ? {id, type, x: 8, y: 8, width: Math.min(70, project.width - 8), height: Math.min(24, project.height - 8), color: rgb565(28, 131, 145), filled: true} : {id, type, x0: 8, y0: 8, x1: Math.min(100, project.width - 1), y1: Math.min(40, project.height - 1), color: 65535};
      page().widgets.push(item); selected = id;
    }); notice("组件已添加，可在画布中拖动。");
  }
  function point(event) { const rect = $("preview").getBoundingClientRect(); return {x: Math.floor((event.clientX - rect.left) * project.width / rect.width), y: Math.floor((event.clientY - rect.top) * project.height / rect.height)}; }
  $("preview").addEventListener("pointerdown", event => {
    const p = point(event);
    const hit = [...page().widgets].reverse().find(w => { const b = bounds(w); return p.x >= b.x && p.y >= b.y && p.x < b.x + b.width && p.y < b.y + b.height; });
    selected = hit ? hit.id : null; dragging = hit ? {point: p, original: copy(hit)} : null;
    $("preview").setPointerCapture(event.pointerId); render();
  });
  $("preview").addEventListener("pointermove", event => {
    if (!dragging || !widget()) return;
    const p = point(event), original = dragging.original, b = bounds(original);
    // Text glyphs may clip at the edge; only its origin must stay on canvas.
    const clampWidth = original.type === "text" ? 1 : Math.min(b.width, project.width);
    const clampHeight = original.type === "text" ? 1 : Math.min(b.height, project.height);
    const dx = Math.max(-b.x, Math.min(project.width - clampWidth - b.x, p.x - dragging.point.x));
    const dy = Math.max(-b.y, Math.min(project.height - clampHeight - b.y, p.y - dragging.point.y));
    const target = widget();
    if (original.type === "line") { target.x0 = original.x0 + dx; target.x1 = original.x1 + dx; target.y0 = original.y0 + dy; target.y1 = original.y1 + dy; }
    else { target.x = original.x + dx; target.y = original.y + dy; }
    render();
  });
  $("preview").addEventListener("pointerup", () => { dragging = null; });
  $("preview").addEventListener("pointercancel", () => { dragging = null; });
  function bind(id, fn) { $(id).addEventListener("click", () => Promise.resolve().then(fn).catch(e => notice(e.message, "error"))); }
  document.querySelectorAll("[data-add]").forEach(button => button.onclick = () => { try { add(button.dataset.add); } catch (e) { notice(e.message, "error"); } });
  bind("add-page", () => transact(() => { assert(project.pages.length < 4, "最多4个页面。"); project.pages.push({id: uniqueId("page", project.pages.map(p => p.id)), background: 0, widgets: []}); pageIndex = project.pages.length - 1; selected = null; }));
  bind("delete-page", () => transact(() => { assert(project.pages.length > 1, "至少保留一个页面。"); project.pages.splice(pageIndex, 1); pageIndex = 0; selected = null; }));
  bind("delete-widget", () => transact(() => { page().widgets = page().widgets.filter(w => w.id !== selected); selected = null; }));
  for (const [id, delta] of [["move-up", 1], ["move-down", -1]]) bind(id, () => transact(() => { const list = page().widgets, i = list.findIndex(w => w.id === selected), j = Math.min(list.length - 1, Math.max(0, i + delta)); [list[i], list[j]] = [list[j], list[i]]; }));
  $("page-id").addEventListener("change", () => { try { transact(() => { page().id = $("page-id").value; }); } catch (e) { notice(e.message, "error"); } });
  $("background").addEventListener("input", () => { page().background = fromHex($("background").value); draw(); $("size-badge").textContent = `${encoder.encode(compact(project)).length} / 8192 字节`; });
  $("canvas-size").addEventListener("change", () => { try { transact(() => { const [width, height] = $("canvas-size").value.split("x").map(Number); project.width = width; project.height = height; for (const p of project.pages) for (const w of p.widgets) { if (w.type === "line") { w.x0 = Math.min(w.x0, width - 1); w.x1 = Math.min(w.x1, width - 1); w.y0 = Math.min(w.y0, height - 1); w.y1 = Math.min(w.y1, height - 1); } else { const b = bounds(w); w.x = Math.max(0, Math.min(w.x, width - Math.min(b.width, width))); w.y = Math.max(0, Math.min(w.y, height - Math.min(b.height, height))); if (w.type === "rect") { w.width = Math.min(w.width, width); w.height = Math.min(w.height, height); } } } }); notice("画布尺寸已更改，请检查组件位置。开发板尺寸需与此一致。"); } catch (e) { notice(e.message, "error"); } });
  bind("json-button", () => { $("json-source").value = JSON.stringify(project, null, 2); $("json-error").textContent = ""; $("json-dialog").showModal(); });
  bind("close-json", () => $("json-dialog").close());
  bind("apply-json", () => { try { setProject(JSON.parse($("json-source").value)); $("json-dialog").close(); notice("JSON验证通过，已应用到电脑画布。", "success"); } catch (error) { const message = error instanceof SyntaxError ? "JSON格式错误：" + error.message : error.message; $("json-error").textContent = message; throw new Error(message); } });
  bind("export-button", () => { validate(project); const blob = new Blob([JSON.stringify(project, null, 2)], {type: "application/json"}); const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = "ai_maker_pages.json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); notice("已导出含图标的页面包；未写入开发板。", "success"); });
  bind("import-button", () => $("project-file").click());
  $("project-file").addEventListener("change", async event => { try { const file = event.target.files[0]; if (!file) return; assert(file.size <= 100000, "JSON文件过大。"); setProject(JSON.parse(await file.text())); notice("页面包导入成功。", "success"); } catch (e) { notice(e.message, "error"); } finally { event.target.value = ""; } });
  bind("image-button", () => $("image-file").click());
  $("image-file").addEventListener("change", async event => {
    let bitmap;
    try {
      const file = event.target.files[0]; if (!file) return;
      assert(["image/png", "image/jpeg", "image/webp"].includes(file.type), "仅接受PNG、JPEG、WebP图标，不支持SVG。"); assert(file.size <= 10 * 1024 * 1024, "原始图片不能超过10MiB。");
      bitmap = await createImageBitmap(file); const edge = Number($("image-size").value), ratio = Math.min(1, edge / Math.max(bitmap.width, bitmap.height));
      const width = Math.max(1, Math.round(bitmap.width * ratio)), height = Math.max(1, Math.round(bitmap.height * ratio));
      const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
      const ctx = canvas.getContext("2d"); ctx.fillStyle = hex(page().background); ctx.fillRect(0, 0, width, height); ctx.drawImage(bitmap, 0, 0, width, height);
      const pixels = ctx.getImageData(0, 0, width, height).data, bytes = [];
      for (let i = 0; i < pixels.length; i += 4) { const c = rgb565(pixels[i], pixels[i + 1], pixels[i + 2]); bytes.push(c >> 8, c & 255); }
      transact(() => { const id = uniqueId("image", project.images.map(i => i.id)), wid = uniqueId("icon", page().widgets.map(w => w.id)); project.images.push({id, width, height, data: bytesTo64(bytes)}); page().widgets.push({id: wid, type: "image", x: Math.max(0, project.width - width - 8), y: 8, asset: id}); selected = wid; });
      notice(`图标已转为${width}×${height} RGB565，随JSON包保存。`, "success");
    } catch (e) { notice(e.message, "error"); } finally { if (bitmap) bitmap.close(); event.target.value = ""; }
  });
  async function api(path, data) { const response = await fetch(path, {method: data === undefined ? "GET" : "POST", headers: {"X-Editor-Token": TOKEN, ...(data === undefined ? {} : {"Content-Type": "application/json"})}, ...(data === undefined ? {} : {body: JSON.stringify(data)})}); const result = await response.json(); if (!response.ok) throw new Error(result.error || "请求失败。"); return result; }
  function setMapping(mapping) {
    if (!mapping) return;
    $("panel").value = mapping.panel; $("rotation").value = mapping.rotation;
    for (const key of ["sck", "mosi", "cs", "dc", "rst", "backlight"]) $("pin-" + key).value = mapping[key];
    if (mapping.invert !== undefined) $("display-invert").value = String(mapping.invert);
    if (mapping.brightness !== undefined) $("display-brightness").value = mapping.brightness;
  }
  function setDevice(data) {
    device = data; const connected = !!data.connected;
    $("connection-badge").textContent = connected ? "已连接开发板" : "离线设计"; $("connection-badge").className = "badge" + (connected ? " online" : "");
    $("connect-button").disabled = connected;
    for (const id of ["disconnect-button", "configure-display"]) $(id).disabled = !connected;
    for (const id of ["read-project", "save-show", "show-page", "startup-enabled", "save-startup"]) $(id).disabled = !(connected && data.info.capabilities?.pages);
    const display = data.status?.display;
    $("device-summary").textContent = connected ? `${data.port} · 固件 ${data.info.firmware_version}${display?.configured ? ` · 屏幕${display.width}×${display.height}` : " · 尚未保存屏幕接线"}${data.info.capabilities?.pages ? "" : " · 需升级0.4页面固件"}` : "未连接。浏览器编辑与预览可独立使用。";
    $("startup-enabled").checked = !!data.pages?.startup_enabled;
    const mapping = data.config?.config?.display;
    setMapping(mapping);
  }
  async function refreshPorts() { const result = await api("/api/ports"), select = $("port"), previous = select.value; select.replaceChildren(); for (const port of [{port: "AUTO", description: "自动选择唯一 USB"}, ...result.ports]) { const option = document.createElement("option"); option.value = port.port; option.textContent = port.port === "AUTO" ? port.description : `${port.port} · ${port.description}`; select.append(option); } if ([...select.options].some(o => o.value === previous)) select.value = previous; }
  bind("refresh-ports", refreshPorts);
  bind("connect-button", async () => { setDevice(await api("/api/connect", {port: $("port").value})); notice("开发板已连接，默认页面已临时交出控制。画布编辑不会自动上传。", "success"); });
  bind("disconnect-button", async () => { setDevice(await api("/api/disconnect", {})); notice("已断开；开发板按已保存的开机设置恢复默认页。", "success"); });
  bind("read-project", async () => { const result = await api("/api/project"); setProject(result.project); notice("已读取开发板保存的页面包。", "success"); });
  bind("save-show", async () => { validate(project); notice("正在保存页面包并显示，请稍候…"); await api("/api/upload", {project, show: true, id: page().id, startup: $("startup-enabled").checked}); setDevice(await api("/api/status")); notice("保存和显示指令已完成，请观察实物画面。", "success"); });
  bind("show-page", async () => { await api("/api/show", {id: page().id}); notice("已发送切页指令；只显示开发板已保存的版本。", "success"); });
  bind("save-startup", async () => { const enabled = $("startup-enabled").checked; await api("/api/startup", enabled ? {enabled: true, id: page().id} : {enabled: false}); setDevice(await api("/api/status")); notice("开机显示设置已保存；断开连接后生效。", "success"); });
  const pinDefaults = {sck: 4, mosi: 5, cs: 15, dc: 7, rst: 6, backlight: 16};
  for (const [key, value] of Object.entries(pinDefaults)) { const wrap = document.createElement("div"); wrap.className = "field"; const label = document.createElement("label"); label.textContent = key === "backlight" ? "BLK (-1为无)" : key.toUpperCase(); label.htmlFor = "pin-" + key; const input = document.createElement("input"); input.type = "number"; input.step = "1"; input.id = "pin-" + key; input.value = value; wrap.append(label, input); $("pin-fields").append(wrap); }
  for (const [id, labelText, choices] of [["display-invert", "颜色反相", ["false", "true"]], ["display-brightness", "背光亮度（0～100%）", null]]) {
    const wrap = document.createElement("div"); wrap.className = "field";
    const label = document.createElement("label"); label.htmlFor = id; label.textContent = labelText;
    const input = document.createElement(choices ? "select" : "input"); input.id = id;
    if (choices) for (const choice of choices) { const option = document.createElement("option"); option.value = option.textContent = choice; input.append(option); }
    else { input.type = "number"; input.min = "0"; input.max = "100"; input.value = "60"; }
    wrap.append(label, input); $("pin-fields").append(wrap);
  }
  bind("configure-display", async () => { const mapping = {panel: $("panel").value, rotation: Number($("rotation").value), invert: $("display-invert").value === "true", brightness: Number($("display-brightness").value)}; for (const key of Object.keys(pinDefaults)) mapping[key] = Number($("pin-" + key).value); const result = await api("/api/configure_display", mapping); setDevice(result.status); notice("屏幕接线已保存到开发板；电脑统一配置不变。尚未初始化显示，请确认画布尺寸后保存并显示。", "success"); });
  async function loadSharedSettings() {
    const settings = await api("/api/settings"); await refreshPorts();
    const select = $("port"), configured = settings.connection.port;
    if (![...select.options].some(o => o.value === configured)) { const option = document.createElement("option"); option.value = configured; option.textContent = configured + " · 配置值（当前未枚举）"; select.append(option); }
    select.value = configured; setMapping(settings.display);
  }
  validate(project); render(); loadSharedSettings().catch(e => notice("统一配置读取失败：" + e.message, "error"));
})();
