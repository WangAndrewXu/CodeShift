"use client";

import { useEffect, useState, ChangeEvent } from "react";

type StatusType = "success" | "error" | "info" | "";
type ProgressStage = "idle" | "upload" | "converting" | "done";

type ProviderConfig = {
  providerName: string;
  apiKey: string;
  baseUrl: string;
  model: string;
};

type PersistedProviderConfig = Omit<ProviderConfig, "apiKey">;

type ProviderTestResponse = {
  success: boolean;
  message: string;
  provider_name?: string;
  model?: string;
  base_url?: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const STORAGE_KEY = "codeshift_provider_config_v1";
const DEFAULT_PROVIDER_CONFIG: ProviderConfig = {
  providerName: "OpenAI",
  apiKey: "",
  baseUrl: "https://api.openai.com/v1",
  model: "gpt-5.4-mini",
};

function normalizePersistedProviderConfig(
  saved: string
): PersistedProviderConfig | null {
  try {
    const parsed = JSON.parse(saved) as Partial<ProviderConfig>;

    return {
      providerName: parsed.providerName || DEFAULT_PROVIDER_CONFIG.providerName,
      baseUrl: parsed.baseUrl || DEFAULT_PROVIDER_CONFIG.baseUrl,
      model: parsed.model || DEFAULT_PROVIDER_CONFIG.model,
    };
  } catch {
    return null;
  }
}

export default function Home() {
  const [fileName, setFileName] = useState("");
  const [finalFileName, setFinalFileName] = useState("");
  const [originalCode, setOriginalCode] = useState("");
  const [finalCode, setFinalCode] = useState("");
  const [originalLanguage, setOriginalLanguage] = useState("");
  const [finalLanguage, setFinalLanguage] = useState("cpp");

  const [isLoading, setIsLoading] = useState(false);
  const [isTestingProvider, setIsTestingProvider] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusType, setStatusType] = useState<StatusType>("");
  const [conversionRule, setConversionRule] = useState("");

  const [allowAiFallback, setAllowAiFallback] = useState(true);
  const [inputMode, setInputMode] = useState<"paste" | "upload">("paste");

  const [progressStage, setProgressStage] = useState<ProgressStage>("idle");
  const [progressPercent, setProgressPercent] = useState(0);

  const [providerConfig, setProviderConfig] =
    useState<ProviderConfig>(DEFAULT_PROVIDER_CONFIG);

  const [showProviderModal, setShowProviderModal] = useState(false);
  const [providerForm, setProviderForm] =
    useState<ProviderConfig>(DEFAULT_PROVIDER_CONFIG);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const normalized = normalizePersistedProviderConfig(saved);
      if (!normalized) {
        setShowProviderModal(true);
        return;
      }

      const nextConfig: ProviderConfig = {
        ...DEFAULT_PROVIDER_CONFIG,
        ...normalized,
      };

      setProviderConfig(nextConfig);
      setProviderForm(nextConfig);
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
      return;
    }

    setShowProviderModal(true);
  }, []);

  function detectLanguage(name: string) {
    const lowerName = name.toLowerCase();

    if (lowerName.endsWith(".py")) return "python";
    if (
      lowerName.endsWith(".cpp") ||
      lowerName.endsWith(".cc") ||
      lowerName.endsWith(".cxx")
    ) {
      return "cpp";
    }
    if (lowerName.endsWith(".java")) return "java";
    if (lowerName.endsWith(".js")) return "javascript";

    return "unknown";
  }

  function getLanguageLabel(value: string) {
    if (value === "cpp") return "C++";
    if (value === "java") return "Java";
    if (value === "python") return "Python";
    if (value === "javascript") return "JavaScript";
    return value || "Unknown";
  }

  function getDefaultFinalLanguage(source: string) {
    if (source === "cpp") return "python";
    return "cpp";
  }

  function getFileExtension(language: string) {
    if (language === "cpp") return "cpp";
    if (language === "java") return "java";
    if (language === "python") return "py";
    if (language === "javascript") return "js";
    return "txt";
  }

  function buildDefaultFinalFileName(originalName: string, targetLang: string) {
    const extension = getFileExtension(targetLang);
    const baseName = originalName.includes(".")
      ? originalName.substring(0, originalName.lastIndexOf("."))
      : originalName || "converted";

    return `${baseName}_converted.${extension}`;
  }

  function updateFinalFileNameExtension(currentName: string, targetLang: string) {
    const extension = getFileExtension(targetLang);
    const baseName = currentName.includes(".")
      ? currentName.substring(0, currentName.lastIndexOf("."))
      : currentName || "converted";

    return `${baseName}.${extension}`;
  }

  function getStatusBoxClasses() {
    if (statusType === "success") {
      return "mt-4 rounded-xl border border-green-300 bg-green-50 px-4 py-3 text-green-800";
    }
    if (statusType === "error") {
      return "mt-4 rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-red-800";
    }
    if (statusType === "info") {
      return "mt-4 rounded-xl border border-blue-300 bg-blue-50 px-4 py-3 text-blue-800";
    }
    return "hidden";
  }

  function getProgressLabel(stage: ProgressStage) {
    if (stage === "idle") return "Waiting";
    if (stage === "upload") return "Loading input";
    if (stage === "converting") return "Converting code";
    if (stage === "done") return "Finished";
    return "Working";
  }

  function resetAllStates() {
    setFileName("");
    setFinalFileName("");
    setOriginalCode("");
    setFinalCode("");
    setOriginalLanguage("");
    setFinalLanguage("cpp");
    setStatusMessage("");
    setStatusType("");
    setConversionRule("");
    setProgressStage("idle");
    setProgressPercent(0);
  }

  function handleClearAll() {
    resetAllStates();
    setInputMode("paste");
    setStatusMessage("All page data cleared.");
    setStatusType("info");
  }

  function saveProviderConfig() {
    const trimmed: ProviderConfig = {
      providerName: providerForm.providerName.trim() || "Custom Provider",
      apiKey: providerForm.apiKey.trim(),
      baseUrl: providerForm.baseUrl.trim() || "https://api.openai.com/v1",
      model: providerForm.model.trim() || "gpt-5.4-mini",
    };
    const persisted: PersistedProviderConfig = {
      providerName: trimmed.providerName,
      baseUrl: trimmed.baseUrl,
      model: trimmed.model,
    };

    setProviderConfig(trimmed);
    setProviderForm(trimmed);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
    setShowProviderModal(false);
    setStatusMessage(
      trimmed.apiKey
        ? "Provider settings saved. API key stays only in this browser session."
        : "Provider settings saved in this browser."
    );
    setStatusType("success");
  }

  function removeProviderConfig() {
    const emptyConfig: ProviderConfig = DEFAULT_PROVIDER_CONFIG;

    setProviderConfig(emptyConfig);
    setProviderForm(emptyConfig);
    window.localStorage.removeItem(STORAGE_KEY);
    setShowProviderModal(true);
    setStatusMessage("Saved provider settings removed, including the in-memory API key.");
    setStatusType("info");
  }

  function fillOpenAIPreset() {
    setProviderForm((prev) => ({
      ...prev,
      providerName: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-5.4-mini",
    }));
  }

  async function handleTestProvider() {
    setIsTestingProvider(true);
    setStatusMessage("Testing provider connection...");
    setStatusType("info");

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };

      if (providerForm.apiKey.trim()) {
        headers["X-API-Key"] = providerForm.apiKey.trim();
      }
      if (providerForm.baseUrl.trim()) {
        headers["X-Base-URL"] = providerForm.baseUrl.trim();
      }
      if (providerForm.model.trim()) {
        headers["X-Model"] = providerForm.model.trim();
      }
      if (providerForm.providerName.trim()) {
        headers["X-Provider-Name"] = providerForm.providerName.trim();
      }

      const response = await fetch(`${API_BASE_URL}/test-provider`, {
        method: "POST",
        headers,
      });

      const data: ProviderTestResponse = await response.json();

      if (!data.success) {
        setStatusMessage(data.message || "Provider test failed.");
        setStatusType("error");
        return;
      }

      setStatusMessage(data.message || "Provider test succeeded.");
      setStatusType("success");
    } catch (error) {
      console.error(error);
      setStatusMessage("Failed to connect to backend during provider test.");
      setStatusType("error");
    } finally {
      setIsTestingProvider(false);
    }
  }

  async function handleFileUpload(event: ChangeEvent<HTMLInputElement>) {
    try {
      setProgressStage("upload");
      setProgressPercent(20);

      const file = event.target.files?.[0];

      if (!file) {
        setStatusMessage("No file selected.");
        setStatusType("error");
        setProgressStage("idle");
        setProgressPercent(0);
        return;
      }

      const detectedLanguage = detectLanguage(file.name);
      const defaultFinalLanguage = getDefaultFinalLanguage(detectedLanguage);
      const content = await file.text();

      resetAllStates();

      setInputMode("upload");
      setFileName(file.name);
      setOriginalLanguage(detectedLanguage);
      setFinalLanguage(defaultFinalLanguage);
      setFinalFileName(buildDefaultFinalFileName(file.name, defaultFinalLanguage));
      setOriginalCode(content);
      setStatusMessage(`Loaded file successfully: ${file.name}`);
      setStatusType("success");
      setProgressStage("idle");
      setProgressPercent(0);

      event.target.value = "";
    } catch (error) {
      console.error(error);
      setStatusMessage("Failed to read file content.");
      setStatusType("error");
      setProgressStage("idle");
      setProgressPercent(0);
    }
  }

  function handleOriginalLanguageChange(newLanguage: string) {
    setOriginalLanguage(newLanguage);

    if (!fileName.trim()) {
      const defaultOutputLanguage = getDefaultFinalLanguage(newLanguage);
      setFinalLanguage(defaultOutputLanguage);

      if (finalFileName.trim()) {
        setFinalFileName(
          updateFinalFileNameExtension(finalFileName, defaultOutputLanguage)
        );
      } else {
        setFinalFileName(`converted.${getFileExtension(defaultOutputLanguage)}`);
      }
    }

    setStatusMessage(`Original language set to ${getLanguageLabel(newLanguage)}.`);
    setStatusType("info");
  }

  function handleFinalLanguageChange(newLanguage: string) {
    setFinalLanguage(newLanguage);

    if (finalFileName.trim()) {
      setFinalFileName(updateFinalFileNameExtension(finalFileName, newLanguage));
    } else if (fileName.trim()) {
      setFinalFileName(buildDefaultFinalFileName(fileName, newLanguage));
    } else {
      setFinalFileName(`converted.${getFileExtension(newLanguage)}`);
    }

    setStatusMessage(`Final language changed to ${getLanguageLabel(newLanguage)}.`);
    setStatusType("info");
  }

  function handleOriginalCodeChange(value: string) {
    setOriginalCode(value);
    setProgressStage("idle");
    setProgressPercent(0);

    if (!fileName.trim() && !originalLanguage) {
      setStatusMessage("Paste code, then choose the original language.");
      setStatusType("info");
    }
  }

  function handlePasteSetup() {
    if (!originalCode.trim()) {
      setStatusMessage("Please paste code first.");
      setStatusType("error");
      return;
    }

    if (!originalLanguage || originalLanguage === "unknown") {
      setStatusMessage("Please choose the original language first.");
      setStatusType("error");
      return;
    }

    if (!finalFileName.trim()) {
      setFinalFileName(`converted.${getFileExtension(finalLanguage)}`);
    }

    setStatusMessage("Code text is ready. Now click Convert Code.");
    setStatusType("success");
  }

  async function handleConvert() {
    if (!originalCode.trim()) {
      setStatusMessage("Please upload or paste original code first.");
      setStatusType("error");
      return;
    }

    if (
      !originalLanguage ||
      !finalLanguage ||
      originalLanguage === "unknown" ||
      finalLanguage === "unknown"
    ) {
      setStatusMessage("Please choose both original and final languages.");
      setStatusType("error");
      return;
    }

    setIsLoading(true);
    setProgressStage("converting");
    setProgressPercent(70);
    setStatusMessage(
      `Converting ${getLanguageLabel(originalLanguage)} -> ${getLanguageLabel(
        finalLanguage
      )}...`
    );
    setStatusType("info");

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };

      if (providerConfig.apiKey.trim()) {
        headers["X-API-Key"] = providerConfig.apiKey.trim();
      }
      if (providerConfig.baseUrl.trim()) {
        headers["X-Base-URL"] = providerConfig.baseUrl.trim();
      }
      if (providerConfig.model.trim()) {
        headers["X-Model"] = providerConfig.model.trim();
      }
      if (providerConfig.providerName.trim()) {
        headers["X-Provider-Name"] = providerConfig.providerName.trim();
      }

      const response = await fetch(`${API_BASE_URL}/convert`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          code: originalCode,
          filename: fileName || "pasted_code.txt",
          source_language: originalLanguage,
          target_language: finalLanguage,
          allow_ai_fallback: allowAiFallback,
        }),
      });

      const data = await response.json();

      if (!data.success) {
        setStatusMessage(data.message || "Conversion failed.");
        setStatusType("error");
        setConversionRule(data.rule || "");
        setProgressStage("idle");
        setProgressPercent(0);
        return;
      }

      setFinalCode(data.converted_code || "");
      setStatusMessage("Conversion successful.");
      setStatusType("success");
      setConversionRule(data.rule || "");
      setProgressStage("done");
      setProgressPercent(100);

      if (!finalFileName.trim()) {
        setFinalFileName(`converted.${getFileExtension(finalLanguage)}`);
      }
    } catch (error) {
      console.error(error);
      setStatusMessage("Failed to connect to backend.");
      setStatusType("error");
      setConversionRule("");
      setProgressStage("idle");
      setProgressPercent(0);
    } finally {
      setIsLoading(false);
    }
  }

  function handleDownload() {
    if (!finalCode.trim()) {
      setStatusMessage("No final code to download.");
      setStatusType("error");
      return;
    }

    const downloadName =
      finalFileName.trim() ||
      buildDefaultFinalFileName(fileName || "converted.txt", finalLanguage);

    const blob = new Blob([finalCode], { type: "text/plain" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = downloadName;
    a.click();

    URL.revokeObjectURL(url);
    setStatusMessage(`Downloaded ${downloadName}`);
    setStatusType("success");
  }

  async function handleCopyOriginalCode() {
    if (!originalCode.trim()) {
      setStatusMessage("No original code to copy.");
      setStatusType("error");
      return;
    }

    try {
      await navigator.clipboard.writeText(originalCode);
      setStatusMessage("Original code copied to clipboard.");
      setStatusType("success");
    } catch (error) {
      console.error(error);
      setStatusMessage("Failed to copy original code.");
      setStatusType("error");
    }
  }

  async function handleCopyFinalCode() {
    if (!finalCode.trim()) {
      setStatusMessage("No final code to copy.");
      setStatusType("error");
      return;
    }

    try {
      await navigator.clipboard.writeText(finalCode);
      setStatusMessage("Final code copied to clipboard.");
      setStatusType("success");
    } catch (error) {
      console.error(error);
      setStatusMessage("Failed to copy final code.");
      setStatusType("error");
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 p-6 md:p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="text-4xl font-bold text-gray-900">CodeShift</h1>
        <p className="mt-3 text-lg text-gray-600">
          Paste code or upload a file, then convert from Original Code to Final Code.
        </p>

        {showProviderModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl">
              <h2 className="text-2xl font-semibold text-gray-900">
                Configure AI provider
              </h2>
              <p className="mt-2 text-sm text-gray-600">
                Enter a provider name, API key, base URL, and model. This works best
                with OpenAI or OpenAI-compatible APIs.
              </p>
              <p className="mt-2 text-sm text-amber-700">
                The API key is kept only for the current browser session and is not
                saved to local storage.
              </p>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Provider name
                  </label>
                  <input
                    type="text"
                    value={providerForm.providerName}
                    onChange={(e) =>
                      setProviderForm((prev) => ({
                        ...prev,
                        providerName: e.target.value,
                      }))
                    }
                    placeholder="OpenAI / OpenRouter / Custom"
                    className="mt-2 w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm text-gray-800 outline-none focus:border-black"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Model
                  </label>
                  <input
                    type="text"
                    value={providerForm.model}
                    onChange={(e) =>
                      setProviderForm((prev) => ({
                        ...prev,
                        model: e.target.value,
                      }))
                    }
                    placeholder="gpt-5.4-mini"
                    className="mt-2 w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm text-gray-800 outline-none focus:border-black"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700">
                    API key
                  </label>
                  <input
                    type="password"
                    value={providerForm.apiKey}
                    onChange={(e) =>
                      setProviderForm((prev) => ({
                        ...prev,
                        apiKey: e.target.value,
                      }))
                    }
                    placeholder="sk-..."
                    className="mt-2 w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm text-gray-800 outline-none focus:border-black"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Base URL
                  </label>
                  <input
                    type="text"
                    value={providerForm.baseUrl}
                    onChange={(e) =>
                      setProviderForm((prev) => ({
                        ...prev,
                        baseUrl: e.target.value,
                      }))
                    }
                    placeholder="https://api.openai.com/v1"
                    className="mt-2 w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm text-gray-800 outline-none focus:border-black"
                  />
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  onClick={fillOpenAIPreset}
                  className="rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm text-gray-800 hover:border-black hover:bg-gray-100"
                >
                  Use OpenAI preset
                </button>

                <button
                  onClick={handleTestProvider}
                  disabled={isTestingProvider}
                  className="rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm text-gray-800 hover:border-black hover:bg-gray-100 disabled:cursor-not-allowed disabled:bg-gray-200"
                >
                  {isTestingProvider ? "Testing..." : "Test Connection"}
                </button>
              </div>

              <div className="mt-6 flex flex-wrap gap-3">
                <button
                  onClick={saveProviderConfig}
                  className="rounded-xl bg-black px-5 py-3 text-white hover:bg-gray-800"
                >
                  Save Provider Settings
                </button>
                <button
                  onClick={() => setShowProviderModal(false)}
                  className="rounded-xl border border-gray-300 bg-white px-5 py-3 text-gray-800 hover:border-black hover:bg-gray-100"
                >
                  Continue without provider
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="mt-6 rounded-2xl border bg-white p-6 shadow-sm">
          <div className="mb-6 rounded-2xl border bg-gray-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Provider settings
                </h2>
                <p className="mt-1 text-sm text-gray-600">
                  Provider: {providerConfig.providerName || "Not set"}
                </p>
                <p className="mt-1 text-sm text-gray-600">
                  Base URL: {providerConfig.baseUrl || "Not set"}
                </p>
                <p className="mt-1 text-sm text-gray-600">
                  Model: {providerConfig.model || "Not set"}
                </p>
                <p className="mt-1 text-sm text-gray-600">
                  API key: {providerConfig.apiKey ? "Loaded for current session only" : "Not loaded"}
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => setShowProviderModal(true)}
                  className="rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm text-gray-800 hover:border-black hover:bg-gray-100"
                >
                  Change Provider Settings
                </button>
                <button
                  onClick={removeProviderConfig}
                  className="rounded-xl border border-red-300 bg-white px-4 py-2 text-sm text-red-600 hover:border-red-500 hover:bg-red-50"
                >
                  Remove Saved Settings
                </button>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setInputMode("paste")}
              className={`rounded-xl px-4 py-2 text-sm font-medium transition ${inputMode === "paste"
                ? "bg-black text-white"
                : "border border-gray-300 bg-white text-gray-800 hover:border-black hover:bg-gray-100"
                }`}
            >
              Paste Code Text
            </button>
            <button
              onClick={() => setInputMode("upload")}
              className={`rounded-xl px-4 py-2 text-sm font-medium transition ${inputMode === "upload"
                ? "bg-black text-white"
                : "border border-gray-300 bg-white text-gray-800 hover:border-black hover:bg-gray-100"
                }`}
            >
              Upload Code File
            </button>
          </div>

          <div className="mt-6 rounded-2xl border border-blue-200 bg-blue-50 p-5">
            <h2 className="text-lg font-semibold text-blue-900">Quick workflow</h2>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-blue-200 bg-white p-4">
                <p className="text-sm font-semibold text-blue-900">Step 1</p>
                <p className="mt-1 text-sm text-gray-700">
                  Paste code or upload a file, then choose the original language.
                </p>
              </div>
              <div className="rounded-xl border border-blue-200 bg-white p-4">
                <p className="text-sm font-semibold text-blue-900">Step 2</p>
                <p className="mt-1 text-sm text-gray-700">
                  Choose the target language and click Convert Code.
                </p>
              </div>
              <div className="rounded-xl border border-blue-200 bg-white p-4">
                <p className="text-sm font-semibold text-blue-900">Step 3</p>
                <p className="mt-1 text-sm text-gray-700">
                  Copy or download the converted result.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border bg-gray-50 p-5">
            <h2 className="text-lg font-semibold text-gray-900">
              Step 1: Add original code
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Pasting code directly is fully supported.
            </p>

            {inputMode === "paste" ? (
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Original language
                  </label>
                  <select
                    value={originalLanguage}
                    onChange={(e) => handleOriginalLanguageChange(e.target.value)}
                    className="mt-2 w-full rounded-xl border border-gray-300 bg-white px-3 py-3 text-sm text-gray-800 outline-none focus:border-black"
                  >
                    <option value="">Choose original language</option>
                    <option value="cpp">C++</option>
                    <option value="java">Java</option>
                    <option value="python">Python</option>
                    <option value="javascript">JavaScript</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Output file name
                  </label>
                  <input
                    type="text"
                    value={finalFileName}
                    onChange={(e) => setFinalFileName(e.target.value)}
                    placeholder="converted.py / converted.cpp / etc."
                    className="mt-2 w-full rounded-xl border border-gray-300 bg-white px-3 py-3 text-sm text-gray-800 outline-none focus:border-black"
                  />
                </div>

                <div className="md:col-span-2">
                  <button
                    onClick={handlePasteSetup}
                    className="rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm text-gray-800 transition hover:border-black hover:bg-gray-100"
                  >
                    Confirm pasted code setup
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-5">
                <label className="block text-sm font-medium text-gray-700">
                  Upload code file
                </label>
                <input
                  type="file"
                  accept=".java,.cpp,.cc,.cxx,.py,.js"
                  onChange={handleFileUpload}
                  className="mt-3 block w-full rounded-xl border border-gray-300 bg-white px-3 py-3 text-sm text-gray-800 file:mr-4 file:rounded-lg file:border-0 file:bg-black file:px-4 file:py-2 file:text-white hover:border-black"
                />
                {fileName && (
                  <p className="mt-3 text-sm text-gray-600">Uploaded file: {fileName}</p>
                )}
              </div>
            )}

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Original language
                </label>
                <div className="mt-2 rounded-xl border bg-white px-3 py-3 text-sm text-gray-800">
                  {originalLanguage
                    ? getLanguageLabel(originalLanguage)
                    : "Not selected yet"}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Target language
                </label>
                <select
                  value={finalLanguage}
                  onChange={(e) => handleFinalLanguageChange(e.target.value)}
                  className="mt-2 w-full rounded-xl border border-gray-300 bg-white px-3 py-3 text-sm text-gray-800 outline-none focus:border-black"
                >
                  <option value="cpp">C++</option>
                  <option value="java">Java</option>
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                </select>
              </div>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border bg-gray-50 p-5">
            <h2 className="text-lg font-semibold text-gray-900">
              Step 2: Convert
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Rule-based conversion is tried first for simple string variables,
              print or log statements, and basic <code>greet(...)</code> examples.
              If those patterns do not match, AI fallback can use the provider settings above.
            </p>

            <div className="mt-5">
              <label className="flex items-center gap-2 rounded-xl border bg-white px-3 py-3 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={allowAiFallback}
                  onChange={(e) => setAllowAiFallback(e.target.checked)}
                />
                Allow AI fallback during convert
              </label>
            </div>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                onClick={handleConvert}
                disabled={isLoading}
                className="rounded-xl bg-black px-5 py-3 text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:bg-gray-400"
              >
                {isLoading ? "Converting..." : "Convert Code"}
              </button>

              <button
                onClick={handleDownload}
                className="rounded-xl border border-gray-300 bg-white px-5 py-3 text-gray-800 transition hover:border-black hover:bg-gray-100"
              >
                Download Final Code
              </button>

              <button
                onClick={handleCopyFinalCode}
                className="rounded-xl border border-gray-300 bg-white px-5 py-3 text-gray-800 transition hover:border-black hover:bg-gray-100"
              >
                Copy Final Code
              </button>

              <button
                onClick={handleClearAll}
                className="rounded-xl border border-red-300 bg-white px-5 py-3 text-red-600 transition hover:border-red-500 hover:bg-red-50"
              >
                Clear All
              </button>
            </div>
          </div>

          <div className="mt-6 rounded-xl border bg-gray-50 p-4">
            <div className="flex items-center justify-between text-sm text-gray-700">
              <span className="font-medium">Progress</span>
              <span>{getProgressLabel(progressStage)}</span>
            </div>
            <div className="mt-3 h-3 w-full overflow-hidden rounded-full bg-gray-200">
              <div
                className="h-full rounded-full bg-black transition-all"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {statusMessage && (
            <div className={getStatusBoxClasses()}>
              <p className="text-base font-semibold">{statusMessage}</p>
              {conversionRule && conversionRule !== statusMessage && (
                <p className="mt-1 text-sm opacity-90">{conversionRule}</p>
              )}
            </div>
          )}
        </div>

        <div className="mt-8 grid gap-6 md:grid-cols-2">
          <div className="rounded-2xl border bg-white p-4 shadow-sm">
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Original Code</h2>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border bg-gray-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-500">
                    Input Source
                  </p>
                  <p className="mt-1 text-sm font-medium text-gray-800">
                    {inputMode === "paste" ? "Pasted text" : "Uploaded file"}
                  </p>
                </div>
                <div className="rounded-xl border bg-gray-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-500">
                    Original Language
                  </p>
                  <p className="mt-1 text-sm font-medium text-gray-800">
                    {getLanguageLabel(originalLanguage)}
                  </p>
                </div>
              </div>
            </div>

            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm text-gray-500">
                Paste code here or edit uploaded code directly
              </span>
              <button
                onClick={handleCopyOriginalCode}
                className="rounded-lg border border-gray-300 bg-white px-3 py-1 text-sm text-gray-700 transition hover:border-black hover:bg-gray-100"
              >
                Copy
              </button>
            </div>

            <textarea
              value={originalCode}
              onChange={(e) => handleOriginalCodeChange(e.target.value)}
              spellCheck={false}
              className="min-h-[520px] w-full resize-y rounded-xl bg-gray-100 p-4 font-mono text-sm text-gray-800 outline-none focus:ring-2 focus:ring-gray-300"
              placeholder="Paste your source code here, or upload a code file in Step 1."
            />
          </div>

          <div className="rounded-2xl border bg-white p-4 shadow-sm">
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Final Code</h2>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border bg-gray-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-500">
                    File Name
                  </p>
                  <input
                    type="text"
                    value={finalFileName}
                    onChange={(e) => setFinalFileName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 outline-none focus:border-black"
                    placeholder="Enter final file name"
                  />
                </div>
                <div className="rounded-xl border bg-gray-50 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-500">
                    Target Language
                  </p>
                  <select
                    value={finalLanguage}
                    onChange={(e) => handleFinalLanguageChange(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-800 outline-none focus:border-black"
                  >
                    <option value="cpp">C++</option>
                    <option value="java">Java</option>
                    <option value="python">Python</option>
                    <option value="javascript">JavaScript</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm text-gray-500">
                Converted result appears here
              </span>
              <button
                onClick={handleCopyFinalCode}
                className="rounded-lg border border-gray-300 bg-white px-3 py-1 text-sm text-gray-700 transition hover:border-black hover:bg-gray-100"
              >
                Copy
              </button>
            </div>

            <textarea
              value={finalCode}
              onChange={(e) => setFinalCode(e.target.value)}
              spellCheck={false}
              className="min-h-[520px] w-full resize-y rounded-xl bg-gray-100 p-4 font-mono text-sm text-gray-800 outline-none focus:ring-2 focus:ring-gray-300"
              placeholder="Your converted code will appear here after conversion."
            />
          </div>
        </div>
      </div>
    </main>
  );
}
