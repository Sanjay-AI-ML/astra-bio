const path = require("path");
module.exports = {
    uiHost: "127.0.0.1",
    uiPort: 1880,
    flowFile: path.resolve(__dirname, "flows.json"),
    credentialSecret: false,
    functionGlobalContext: {},
    logging: { console: { level: "info", metrics: false, audit: false } },
    editorTheme: { projects: { enabled: false } }
};
