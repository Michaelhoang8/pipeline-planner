// Shared lifecycle for stateless analyses; never retries mutations automatically.
(() => {
  let active = null,
    cancelButton = null;
  document.addEventListener("DOMContentLoaded", () => {
    const run = document.querySelector("#run");
    if (
      !run ||
      document.body.dataset.app === "rest" ||
      location.pathname === "/rest"
    )
      return;
    cancelButton = document.createElement("button");
    cancelButton.id = "cancel-analysis";
    cancelButton.type = "button";
    cancelButton.textContent = "Cancel analysis";
    cancelButton.hidden = true;
    cancelButton.addEventListener("click", () => active?.controller.abort());
    run.after(cancelButton);
  });
  window.addEventListener("hashchange", () => active?.controller.abort());
  window.addEventListener("pagehide", () => active?.controller.abort());
  window.analysisRequest = async (path, body) => {
    const request = { controller: new AbortController(), timedOut: false };
    active = request;
    if (cancelButton) {
      cancelButton.hidden = false;
      cancelButton.disabled = false;
    }
    const timeout = setTimeout(() => {
      request.timedOut = true;
      request.controller.abort();
    }, 60000);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Portfolio-Client": "browser",
        },
        body: JSON.stringify(body),
        signal: request.controller.signal,
      });
      let data;
      try {
        data = await response.json();
      } catch (error) {
        if (error.name === "AbortError") throw error;
        throw Error(
          "The server returned an unreadable response. Check the server and try again.",
        );
      }
      if (!data || typeof data !== "object" || Array.isArray(data))
        throw Error(
          "The server returned an unreadable response. Check the server and try again.",
        );
      if (!response.ok)
        throw Error(
          typeof data.error === "string" && data.error
            ? data.error
            : `Analysis failed (HTTP ${response.status}).`,
        );
      return data;
    } catch (error) {
      if (error.name === "AbortError")
        throw Error(
          request.timedOut
            ? "The analysis timed out after 60 seconds. Your input is preserved; try a smaller dataset."
            : "Analysis cancelled. Your input is preserved.",
        );
      if (error instanceof TypeError)
        throw Error(
          "Could not reach the local server. Check that it is running, then try again.",
        );
      throw error;
    } finally {
      clearTimeout(timeout);
      if (active === request) {
        active = null;
        if (cancelButton) {
          cancelButton.hidden = true;
          cancelButton.disabled = true;
        }
      }
    }
  };
})();
