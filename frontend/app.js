// Адрес бэкенда. Пустая строка = тот же сервер, с которого открыта страница.
// Если открываешь фронт отдельно (например, Live Server), впиши: "http://127.0.0.1:8000"
const API = "";

const STATUS_NAMES = {
  active: "Активно",
  review: "На проверке",
  blocked: "Заблокировано",
};

// ---------- общие функции ----------

// запрос к бэкенду, возвращает JSON
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

// защита от подстановки html в текст
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

// ---------- Обзор ----------

async function initDashboard() {
  const stats = await api("/api/stats");
  for (const key of ["users", "active", "review", "blocked"]) {
    document.getElementById("stat-" + key).textContent = stats[key];
  }

  const latest = await api("/api/listings?limit=4");
  document.getElementById("rows").innerHTML = latest
    .map(
      (x) => `
      <tr>
        <td>${esc(x.title)}</td>
        <td>${esc(x.author)}</td>
        <td class="${x.status}">${STATUS_NAMES[x.status]}</td>
      </tr>`
    )
    .join("");
}

// ---------- Объявления ----------

async function loadListings() {
  const items = await api("/api/listings");
  document.getElementById("rows").innerHTML = items
    .map(
      (x) => `
      <tr>
        <td>${esc(x.title)}</td>
        <td>${esc(x.category || "—")}</td>
        <td>${esc(x.want)}</td>
        <td>${esc(x.author)}</td>
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

// ---------- Пользователи ----------

async function loadUsers() {
  const items = await api("/api/users");
  document.getElementById("rows").innerHTML = items
    .map(
      (u) => `
      <tr>
        <td>${esc(u.name)}</td>
        <td>${esc(u.email)}</td>
        <td>${esc(u.city)}</td>
        <td>${u.listings_count}</td>
        <td>${fmtDate(u.created_at)}</td>
        <td class="${u.is_blocked ? "blocked" : "active"}">${u.is_blocked ? "Заблокирован" : "Активен"}</td>
        <td><button data-id="${u.id}">${u.is_blocked ? "Разблокировать" : "Заблокировать"}</button></td>
      </tr>`
    )
    .join("");
}

async function initUsers() {
  await loadUsers();
  document.getElementById("rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    try {
      await api(`/api/users/${btn.dataset.id}/toggle-block`, { method: "POST" });
      await loadUsers();
    } catch (err) {
      showError(err.message);
    }
  });
}

// ---------- Категории ----------

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

// ---------- запуск: смотрим, на какой мы странице ----------

const pages = {
  dashboard: initDashboard,
  listings: initListings,
  users: initUsers,
  categories: initCategories,
};

const init = pages[document.body.dataset.page];
if (init) {
  init().catch(() => showError());
}
