(() => {
  const record = (type, message) => {
    console.log(`[dialog:${type}] ${String(message ?? "")}`);
  };

  window.alert = (message) => {
    record("alert", message);
  };

  window.confirm = (message) => {
    record("confirm", message);
    return true;
  };

  window.prompt = (message, defaultValue = "") => {
    record("prompt", message);
    return defaultValue;
  };
})();
