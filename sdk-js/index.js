const https = require("https");
const http = require("http");

class ChainThread {
  constructor(baseUrl = "https://chain-thread.onrender.com") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  _request(method, path, body = null) {
    return new Promise((resolve, reject) => {
      const url = new URL(this.baseUrl + path);
      const lib = url.protocol === "https:" ? https : http;
      const options = {
        hostname: url.hostname,
        port: url.port || (url.protocol === "https:" ? 443 : 80),
        path: url.pathname + url.search,
        method,
        headers: { "Content-Type": "application/json" },
      };
      const req = lib.request(options, (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          try { resolve(JSON.parse(data)); }
          catch (e) { resolve(data); }
        });
      });
      req.on("error", reject);
      if (body) req.write(JSON.stringify(body));
      req.end();
    });
  }

  // --- Chains ---
  createChain(name, description = null, tags = {}) {
    return this._request("POST", "/chains", { name, description, tags });
  }

  listChains() {
    return this._request("GET", "/chains");
  }

  // --- Envelopes ---
  sendEnvelope(chainId, senderId, senderRole, receiverId, receiverRole, payload, summary, provenance = [], contract = {}, onFail = "block") {
    return this._request("POST", "/envelopes", {
      chain_id: chainId,
      sender_id: senderId,
      sender_role: senderRole,
      receiver_id: receiverId,
      receiver_role: receiverRole,
      payload,
      summary,
      provenance,
      contract,
      on_fail: onFail,
    });
  }

  getEnvelope(envelopeId) {
    return this._request("GET", `/envelopes/${envelopeId}`);
  }

  getChainEnvelopes(chainId) {
    return this._request("GET", `/chains/${chainId}/envelopes`);
  }

  validateEnvelope(envelopeId) {
    return this._request("POST", `/envelopes/${envelopeId}/validate`);
  }

  // --- Violations ---
  getViolations() {
    return this._request("GET", "/violations");
  }

  // --- Checkpoints ---
  createCheckpoint(chainId, stateSnapshot, envelopeId = null, checkpointName = null) {
    return this._request("POST", "/checkpoints", {
      chain_id: chainId,
      envelope_id: envelopeId,
      state_snapshot: stateSnapshot,
      checkpoint_name: checkpointName,
    });
  }

  getCheckpoints(chainId) {
    return this._request("GET", `/checkpoints/${chainId}`);
  }

  // --- Dashboard ---
  stats() {
    return this._request("GET", "/dashboard/stats");
  }

  health() {
    return this._request("GET", "/health");
  }

  // --- Dead Letter Queue ---
  listDlq(status = null) {
    const path = status ? `/dlq?status=${status}` : "/dlq";
    return this._request("GET", path);
  }

  getDlqRecord(dlqId) {
    return this._request("GET", `/dlq/${dlqId}`);
  }

  patchDlq(dlqId, fieldPatches) {
    return this._request("POST", `/dlq/${dlqId}/patch`, { field_patches: fieldPatches });
  }

  reinjectDlq(dlqId) {
    return this._request("POST", `/dlq/${dlqId}/reinject`, {});
  }

  dropDlq(dlqId, reason = "") {
    return this._request("POST", `/dlq/${dlqId}/drop`, { reason });
  }

  // --- Lineage ---
  getLineageTrace(traceId) {
    return this._request("GET", `/lineage/trace/${traceId}`);
  }

  getChainLineage(chainId) {
    return this._request("GET", `/lineage/chain/${chainId}`);
  }

  // --- Analytics ---
  analyticsChains() {
    return this._request("GET", "/analytics/chains");
  }

  analyticsAgents() {
    return this._request("GET", "/analytics/agents");
  }

  analyticsConfidence() {
    return this._request("GET", "/analytics/confidence");
  }

  analyticsViolations() {
    return this._request("GET", "/analytics/violations");
  }

  // --- Bidirectional Contracts ---
  respondToEnvelope(envelopeId, chainId, responderId, responderRole, responsePayload, responseContract = {}) {
    return this._request("POST", `/envelopes/${envelopeId}/respond`, {
      chain_id: chainId,
      responder_id: responderId,
      responder_role: responderRole,
      response_payload: responsePayload,
      response_contract: responseContract
    });
  }

  getEnvelopeResponses(envelopeId) {
    return this._request("GET", `/envelopes/${envelopeId}/responses`);
  }
}

module.exports = { ChainThread };