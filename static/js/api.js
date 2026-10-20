const API = {
  async request(path, options = {}) {
    const res = await fetch(path, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return { status: res.status, data: await res.json() };
    }
    return { status: res.status, html: await res.text() };
  },

  get(path) { return this.request(path, { method: "GET" }); },
  post(path, body) {
    return this.request(path, {
      method: "POST",
      body: JSON.stringify(body || {}),
    });
  },
};