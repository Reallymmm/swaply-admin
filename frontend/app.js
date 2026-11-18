
const API = "";

const STATUS_NAMES = {
  active: "Активно",
  review: "На проверке",
  blocked: "Заблокировано",
  hidden: "Скрыто автором",
};

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка " + res.status);
  }
  return res.json();
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString("ru-RU");
}

function showError(message) {
  const box = document.getElementById("error");
  if (message) box.textContent = message;
  box.classList.remove("hidden");
}

function thumb(path, cls = "thumb") {
  return path ? `<img class="${cls}" src="${API + path}" alt="">` : "—";
}

function ratingText(rating, count) {
  return rating ? `★ ${rating} (${count})` : "нет отзывов";
}

function hideMessages() {
  document.getElementById("error").classList.add("hidden");
  const ok = document.getElementById("ok");
  if (ok) ok.classList.add("hidden");
}

function showOk(message) {
  const box = document.getElementById("ok");
  box.textContent = message;
  box.classList.remove("hidden");
}


const APPEAL_NAMES = { pending: "На рассмотрении", approved: "Одобрена", rejected: "Отклонена" };
const REVIEW_NAMES = { visible: "Виден", hidden: "Скрыт" };

function stars(n) {
  return "★".repeat(n) + "☆".repeat(5 - n);
}

// Окно с полями. fields: [{name, label, type: "select"|"textarea", options?}]. Возвращает значения или null.
function openDialog(title, fields, okText) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.innerHTML = `
      <form method="dialog">
        <h3>${esc(title)}</h3>
        ${fields
          .map((f) =>
            f.type === "select"
              ? `<label>${esc(f.label)}<select name="${f.name}">${f.options
                  .map((o) => `<option value="${esc(o.key)}">${esc(o.name)}</option>`)
                  .join("")}</select></label>`
              : `<label>${esc(f.label)}<textarea name="${f.name}" maxlength="${f.max || 300}"></textarea></label>`
          )
          .join("")}
        <p id="dlg-error" class="blocked hidden"></p>
        <div class="dialog-buttons">
          <button type="button" data-cancel>Отмена</button>
          <button type="submit">${esc(okText)}</button>
        </div>
      </form>`;
    document.body.appendChild(dlg);
    const finish = (value) => {
      dlg.close();
      dlg.remove();
      resolve(value);
    };
    dlg.querySelector("[data-cancel]").onclick = () => finish(null);
    dlg.addEventListener("cancel", (e) => {
      e.preventDefault();
      finish(null);
    });
    dlg.querySelector("form").onsubmit = (e) => {
      e.preventDefault();
      const values = {};
      for (const f of fields) values[f.name] = dlg.querySelector(`[name="${f.name}"]`).value.trim();
      for (const f of fields) {
        if (f.required && !values[f.name]) {
          const box = dlg.querySelector("#dlg-error");
          box.textContent = `Заполните поле: ${f.label}`;
          box.classList.remove("hidden");
          return;
        }
      }
      finish(values);
    };
    dlg.showModal();
  });
}

// Выбор причины блокировки из списка. Возвращает {reason, comment} или null.
async function askBlock(name) {
  const reasons = await api("/api/ban-reasons");
  const res = await openDialog(
    `Заблокировать: ${name}`,
    [
      { name: "reason", label: "Причина блокировки", type: "select", options: reasons },
      { name: "comment", label: "Комментарий (обязателен для «Другое»)", type: "textarea" },
    ],
    "Заблокировать"
  );
  if (!res) return null;
  if (res.reason === "other" && !res.comment) {
    showError("Для причины «Другое» напишите комментарий");
    return null;
  }
  return res;
}

async function blockUser(id, name) {
  const res = await askBlock(name);
  if (!res) return false;
  await api(`/api/users/${id}/block`, { method: "POST", body: JSON.stringify(res) });
  return true;
}

async function unblockUser(id) {
  await api(`/api/users/${id}/unblock`, { method: "POST" });
  return true;
}

async function resolveAppeal(id, decision) {
  const res = await openDialog(
    decision === "approve" ? "Одобрить апелляцию (снять блокировку)" : "Отклонить апелляцию",
    [{ name: "comment", label: decision === "reject" ? "Ответ пользователю (обязательно)" : "Ответ пользователю", type: "textarea", max: 1000, required: decision === "reject" }],
    decision === "approve" ? "Одобрить" : "Отклонить"
  );
  if (!res) return false;
  await api(`/api/appeals/${id}/resolve`, { method: "POST", body: JSON.stringify({ decision, comment: res.comment }) });
  return true;
}

async function reviewAction(id, action) {
  if (action === "delete") {
    if (!confirm("Удалить отзыв навсегда?")) return false;
    await api(`/api/reviews/${id}`, { method: "DELETE" });
  } else {
    await api(`/api/reviews/${id}/status`, { method: "POST", body: JSON.stringify({ status: action }) });
  }
  return true;
}

function reviewButtons(r) {
  return `${r.status === "visible" ? `<button data-review="${r.id}" data-action="hidden">Скрыть</button>` : `<button data-review="${r.id}" data-action="visible">Показать</button>`}
          <button data-review="${r.id}" data-action="delete">Удалить</button>`;
}

async function initDashboard() {
  const stats = await api("/api/stats");
  for (const key of ["users", "active", "review", "blocked", "appeals"]) {
    document.getElementById("stat-" + key).textContent = stats[key];
  }

  const latest = await api("/api/listings?limit=4");
  document.getElementById("rows").innerHTML = latest
    .map(
      (x) => `
      <tr>
        <td><a href="listing.html?id=${x.id}">${esc(x.title)}</a></td>
        <td><a href="user.html?id=${x.author_id}">${esc(x.author)}</a></td>
        <td class="${x.status}">${STATUS_NAMES[x.status]}</td>
      </tr>`
    )
    .join("");
}


async function loadListings() {
  const items = await api("/api/listings");
  document.getElementById("rows").innerHTML = items
    .map(
      (x) => `
      <tr>
        <td>${thumb(x.cover)}</td>
        <td><a href="listing.html?id=${x.id}">${esc(x.title)}</a></td>
        <td>${esc(x.category || "—")}</td>
        <td>${esc(x.want)}</td>
        <td><a href="user.html?id=${x.author_id}">${esc(x.author)}</a></td>
        <td>${fmtDate(x.created_at)}</td>
        <td class="${x.status}">${STATUS_NAMES[x.status]}</td>
        <td>
          ${x.status !== "active" ? `<button data-id="${x.id}" data-status="active">Одобрить</button>` : ""}
          ${x.status !== "blocked" ? `<button data-id="${x.id}" data-status="blocked">Заблокировать</button>` : ""}
        </td>
      </tr>`
    )
    .join("");
}

async function initListings() {
  await loadListings();
  document.getElementById("rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    try {
      await api(`/api/listings/${btn.dataset.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: btn.dataset.status }),
      });
      await loadListings();
    } catch (err) {
      showError(err.message);
    }
  });
}


async function loadUsers() {
  const items = await api("/api/users");
  document.getElementById("rows").innerHTML = items
    .map(
      (u) => `
      <tr>
        <td>${u.avatar ? thumb(u.avatar, "thumb-round") + " " : ""}<a href="user.html?id=${u.id}">${esc(u.name)}</a></td>
        <td>${esc(u.email)}</td>
        <td>${esc(u.city)}</td>
        <td>${u.listings_count}</td>
        <td>${fmtDate(u.created_at)}</td>
        <td class="${u.is_blocked ? "blocked" : "active"}">${u.is_blocked ? "Заблокирован" : "Активен"}${u.ban_reason_name ? `<br><small>${esc(u.ban_reason_name)}</small>` : ""}</td>
        <td><button data-id="${u.id}" data-name="${esc(u.name)}" data-blocked="${u.is_blocked}">${u.is_blocked ? "Разблокировать" : "Заблокировать"}</button></td>
      </tr>`
    )
    .join("");
}

async function initUsers() {
  await loadUsers();
  document.getElementById("rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    hideMessages();
    try {
      const done = btn.dataset.blocked === "true"
        ? await unblockUser(btn.dataset.id)
        : await blockUser(btn.dataset.id, btn.dataset.name);
      if (done) await loadUsers();
    } catch (err) {
      showError(err.message);
    }
  });
}


async function initListing() {
  const id = new URLSearchParams(location.search).get("id");
  const content = document.getElementById("content");

  async function load() {
    const x = await api(`/api/listings/${id}`);
    document.title = x.title + " — Swaply Admin";

    const photos = x.photos.length
      ? x.photos.map((p) => `<a href="${API + p.url}" target="_blank"><img class="photo" src="${API + p.url}" alt=""></a>`).join("")
      : `<p class="empty">У объявления нет фотографий</p>`;

    content.innerHTML = `
      <p><a href="listings.html">← К списку объявлений</a></p>
      <h1>${esc(x.title)}</h1>
      <div class="gallery">${photos}</div>
      <table class="info">
        <tr><th>Статус</th><td class="${x.status}">${STATUS_NAMES[x.status]}</td></tr>
        <tr><th>Категория</th><td>${esc(x.category || "—")}</td></tr>
        <tr><th>Хочет взамен</th><td>${esc(x.want)}</td></tr>
        <tr><th>Город</th><td>${esc(x.city)}</td></tr>
        <tr><th>Автор</th><td><a href="user.html?id=${x.author_id}">${esc(x.author)}</a></td></tr>
        <tr><th>Дата</th><td>${fmtDate(x.created_at)}</td></tr>
        <tr><th>Описание</th><td>${esc(x.description)}</td></tr>
      </table>
      <p class="actions">
        ${x.status !== "active" ? `<button data-status="active">Одобрить</button>` : ""}
        ${x.status !== "blocked" ? `<button data-status="blocked">Заблокировать</button>` : ""}
      </p>`;
  }

  await load();
  content.addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    hideMessages();
    try {
      await api(`/api/listings/${id}/status`, { method: "POST", body: JSON.stringify({ status: btn.dataset.status }) });
      await load();
    } catch (err) {
      showError(err.message);
    }
  });
}


async function initUser() {
  const id = new URLSearchParams(location.search).get("id");
  const content = document.getElementById("content");

  async function load() {
    const u = await api(`/api/users/${id}`);
    document.title = u.name + " — Swaply Admin";

    const avatar = u.avatar
      ? `<img class="avatar-big" src="${API + u.avatar}" alt="">`
      : `<div class="avatar-big avatar-letter">${esc(u.name[0])}</div>`;

    const listings = u.listings.length
      ? `<table>
          <thead><tr><th>Фото</th><th>Название</th><th>Категория</th><th>Дата</th><th>Статус</th></tr></thead>
          <tbody>${u.listings
            .map(
              (x) => `<tr>
                <td>${thumb(x.cover)}</td>
                <td><a href="listing.html?id=${x.id}">${esc(x.title)}</a></td>
                <td>${esc(x.category || "—")}</td>
                <td>${fmtDate(x.created_at)}</td>
                <td class="${x.status}">${STATUS_NAMES[x.status]}</td>
              </tr>`
            )
            .join("")}</tbody>
        </table>`
      : `<p class="empty">Объявлений пока нет</p>`;

    const reviews = u.reviews.length
      ? `<table>
          <thead><tr><th>Кто оставил</th><th>Оценка</th><th>Отзыв</th><th>Дата</th><th>Статус</th><th>Действия</th></tr></thead>
          <tbody>${u.reviews
            .map(
              (r) => `<tr class="${r.status === "hidden" ? "hiddenrev" : ""}">
                <td><a href="user.html?id=${r.author_id}">${esc(r.author)}</a></td>
                <td>${stars(r.rating)}</td>
                <td class="wrap-text">${esc(r.text || "—")}</td>
                <td>${fmtDate(r.created_at)}</td>
                <td>${REVIEW_NAMES[r.status]}</td>
                <td>${reviewButtons(r)}</td>
              </tr>`
            )
            .join("")}</tbody>
        </table>`
      : `<p class="empty">Отзывов пока нет</p>`;

    const appeals = u.appeals.length
      ? `<table>
          <thead><tr><th>Дата</th><th>Апелляция</th><th>Статус</th><th>Ответ</th><th>Действия</th></tr></thead>
          <tbody>${u.appeals
            .map(
              (a) => `<tr>
                <td>${fmtDate(a.created_at)}</td>
                <td class="wrap-text">${esc(a.text)}</td>
                <td class="${a.status}">${APPEAL_NAMES[a.status]}</td>
                <td class="wrap-text">${esc(a.admin_comment || "—")}</td>
                <td>${a.status === "pending" ? `<button data-appeal="${a.id}" data-action="approve">Одобрить</button><button data-appeal="${a.id}" data-action="reject">Отклонить</button>` : ""}</td>
              </tr>`
            )
            .join("")}</tbody>
        </table>`
      : `<p class="empty">Апелляций нет</p>`;

    content.innerHTML = `
      <p><a href="users.html">← К списку пользователей</a></p>
      <h1>${esc(u.name)}</h1>
      <div class="profile">
        ${avatar}
        <div>
          <form id="name-form" class="form-row">
            <input id="name-input" value="${esc(u.name)}" maxlength="100" placeholder="ФИО">
            <button type="submit">Сохранить ФИО</button>
          </form>
          <table class="info">
            <tr><th>Email</th><td>${esc(u.email)}</td></tr>
            <tr><th>Город</th><td>${esc(u.city)}</td></tr>
            <tr><th>Регистрация</th><td>${fmtDate(u.created_at)}</td></tr>
            <tr><th>Статус</th><td class="${u.is_blocked ? "blocked" : "active"}">${u.is_blocked ? "Заблокирован" : "Активен"}</td></tr>
            ${u.is_blocked ? `<tr><th>Причина блокировки</th><td>${esc(u.ban_reason_name || "—")}${u.ban_comment ? `<br>${esc(u.ban_comment)}` : ""}</td></tr>` : ""}
            <tr><th>Рейтинг</th><td>${ratingText(u.rating, u.reviews_count)}</td></tr>
          </table>
          <p class="actions">
            <button data-action="block">${u.is_blocked ? "Разблокировать" : "Заблокировать"}</button>
            ${u.avatar ? `<button data-action="del-avatar">Удалить аватарку</button>` : ""}
          </p>
        </div>
      </div>
      <h2>Объявления (${u.listings.length})</h2>
      ${listings}
      <h2>Отзывы (${u.reviews.length})</h2>
      ${reviews}
      <h2>Апелляции (${u.appeals.length})</h2>
      ${appeals}`;
  }

  await load();

  content.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideMessages();
    try {
      await api(`/api/users/${id}`, {
        method: "PUT",
        body: JSON.stringify({ name: document.getElementById("name-input").value }),
      });
      await load();
      showOk("ФИО сохранено");
    } catch (err) {
      showError(err.message);
    }
  });

  content.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    hideMessages();
    try {
      if (btn.dataset.review) {
        if (!(await reviewAction(btn.dataset.review, btn.dataset.action))) return;
      } else if (btn.dataset.appeal) {
        if (!(await resolveAppeal(btn.dataset.appeal, btn.dataset.action))) return;
      } else if (btn.dataset.action === "block") {
        const u = await api(`/api/users/${id}`);
        const done = u.is_blocked ? await unblockUser(id) : await blockUser(id, u.name);
        if (!done) return;
      } else if (btn.dataset.action === "del-avatar") {
        if (!confirm("Удалить аватарку пользователя?")) return;
        await api(`/api/users/${id}/avatar`, { method: "DELETE" });
      }
      await load();
    } catch (err) {
      showError(err.message);
    }
  });
}


async function loadCategories() {
  const items = await api("/api/categories");
  document.getElementById("rows").innerHTML = items
    .map(
      (c) => `
      <tr>
        <td>${esc(c.name)}</td>
        <td>${c.listings_count}</td>
        <td><button data-id="${c.id}">Удалить</button></td>
      </tr>`
    )
    .join("");
}

async function initCategories() {
  await loadCategories();

  document.getElementById("add-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("new-name");
    try {
      await api("/api/categories", {
        method: "POST",
        body: JSON.stringify({ name: input.value }),
      });
      input.value = "";
      await loadCategories();
    } catch (err) {
      showError(err.message);
    }
  });

  document.getElementById("rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    try {
      await api(`/api/categories/${btn.dataset.id}`, { method: "DELETE" });
      await loadCategories();
    } catch (err) {
      showError(err.message);
    }
  });
}


async function loadAppeals() {
  const status = document.getElementById("filter").value;
  const items = await api("/api/appeals" + (status ? `?status=${status}` : ""));
  document.getElementById("rows").innerHTML = items.length
    ? items
        .map(
          (a) => `
      <tr>
        <td>${fmtDate(a.created_at)}</td>
        <td><a href="user.html?id=${a.user_id}">${esc(a.user)}</a><br><small>${esc(a.email)}</small></td>
        <td>${esc(a.ban_reason_name || "—")}${a.ban_comment && a.is_blocked ? `<br><small>${esc(a.ban_comment)}</small>` : ""}</td>
        <td class="wrap-text">${esc(a.text)}</td>
        <td class="${a.status}">${APPEAL_NAMES[a.status]}${a.admin_comment ? `<br><small>${esc(a.admin_comment)}</small>` : ""}</td>
        <td>${a.status === "pending" ? `<button data-id="${a.id}" data-action="approve">Одобрить</button><button data-id="${a.id}" data-action="reject">Отклонить</button>` : ""}</td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="6">Апелляций нет</td></tr>`;
}

async function initAppeals() {
  await loadAppeals();
  document.getElementById("filter").addEventListener("change", loadAppeals);
  document.getElementById("rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    hideMessages();
    try {
      if (await resolveAppeal(btn.dataset.id, btn.dataset.action)) await loadAppeals();
    } catch (err) {
      showError(err.message);
    }
  });
}


async function loadReviews() {
  const status = document.getElementById("filter").value;
  const items = await api("/api/reviews" + (status ? `?status=${status}` : ""));
  document.getElementById("rows").innerHTML = items.length
    ? items
        .map(
          (r) => `
      <tr class="${r.status === "hidden" ? "hiddenrev" : ""}">
        <td>${fmtDate(r.created_at)}</td>
        <td><a href="user.html?id=${r.seller_id}">${esc(r.seller)}</a></td>
        <td><a href="user.html?id=${r.author_id}">${esc(r.author)}</a></td>
        <td>${stars(r.rating)}</td>
        <td class="wrap-text">${esc(r.text || "—")}</td>
        <td>${REVIEW_NAMES[r.status]}</td>
        <td>${reviewButtons(r)}</td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="7">Отзывов нет</td></tr>`;
}

async function initReviews() {
  await loadReviews();
  document.getElementById("filter").addEventListener("change", loadReviews);
  document.getElementById("rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    hideMessages();
    try {
      if (await reviewAction(btn.dataset.review, btn.dataset.action)) await loadReviews();
    } catch (err) {
      showError(err.message);
    }
  });
}


const pages = {
  dashboard: initDashboard,
  listings: initListings,
  users: initUsers,
  listing: initListing,
  user: initUser,
  categories: initCategories,
  appeals: initAppeals,
  reviews: initReviews,
};

const init = pages[document.body.dataset.page];
if (init) {
  init().catch((err) => showError(err instanceof TypeError ? undefined : err.message));
}
