// AI Notemaker - Enterprise Frontend Logic
document.addEventListener("DOMContentLoaded", () => {
  // Elements - Tabs & Views
  const tabConfig = document.getElementById("tabConfig");
  const tabPreview = document.getElementById("tabPreview");
  const configView = document.getElementById("configView");
  const previewView = document.getElementById("previewView");
  const btnGoToConfig = document.getElementById("btnGoToConfig");

  // Elements - Source Material (Mandatory Upload & Chapter)
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const btnChooseFile = document.getElementById("btnChooseFile");
  const fileStatusLabel = document.getElementById("fileStatusLabel");
  const dropZonePrompt = document.getElementById("dropZonePrompt");
  const fileCard = document.getElementById("fileCard");
  const fileNameDisplay = document.getElementById("fileNameDisplay");
  const fileMetaDisplay = document.getElementById("fileMetaDisplay");
  const fileCardIcon = document.getElementById("fileCardIcon");
  const removeFileBtn = document.getElementById("removeFileBtn");
  const manualChapterInput = document.getElementById("manualChapterInput");

  // Elements - Notemaker Settings (Mandatory Checkbox Fields & Generate)
  const cardSummary = document.getElementById("cardSummary");
  const chkSummary = document.getElementById("chkSummary");
  const cardExhaustive = document.getElementById("cardExhaustive");
  const chkExhaustive = document.getElementById("chkExhaustive");
  const btnSummarize = document.getElementById("btnSummarize");

  // Elements - Output & Preview
  const previewCardTitle = document.getElementById("previewCardTitle");
  const emptyState = document.getElementById("emptyState");
  const loadingState = document.getElementById("loadingState");
  const loadingStageTitle = document.getElementById("loadingStageTitle");
  const loadingStageDesc = document.getElementById("loadingStageDesc");
  const notesResult = document.getElementById("notesResult");
  const outputActions = document.getElementById("outputActions");
  const markdownOutput = document.getElementById("markdownOutput");

  const metaFilename = document.getElementById("metaFilename");
  const metaWords = document.getElementById("metaWords");
  const metaScope = document.getElementById("metaScope");

  const btnCopy = document.getElementById("btnCopy");
  const btnPdf = document.getElementById("btnPdf");
  const alertBox = document.getElementById("alertBox");
  const alertTitle = document.getElementById("alertTitle");
  const alertMessage = document.getElementById("alertMessage");
  const toast = document.getElementById("toast");

  // State
  let selectedFile = null;
  let currentRawMarkdown = "";

  // --- View Tabs Navigation ---
  function switchToTab(tabName) {
    if (tabName === "config") {
      tabConfig.classList.add("active");
      tabPreview.classList.remove("active");
      configView.classList.add("active");
      previewView.classList.remove("active");
    } else if (tabName === "preview") {
      tabPreview.classList.add("active");
      tabConfig.classList.remove("active");
      previewView.classList.add("active");
      configView.classList.remove("active");
    }
  }

  tabConfig.addEventListener("click", () => switchToTab("config"));
  tabPreview.addEventListener("click", () => switchToTab("preview"));
  if (btnGoToConfig) {
    btnGoToConfig.addEventListener("click", () => switchToTab("config"));
  }

  // --- Collapsible Cards Support ---
  document.querySelectorAll(".card-vts-collapse-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const targetId = btn.getAttribute("data-target");
      const card = document.getElementById(targetId);
      if (card) {
        const isCollapsed = card.classList.toggle("collapsed");
        btn.textContent = isCollapsed ? "+" : "−";
      }
    });
  });

  // --- Checkbox Option Cards Click & Toggle ---
  function updateOptionCards() {
    if (cardSummary && chkSummary) {
      cardSummary.classList.toggle("checked", chkSummary.checked);
    }
    if (cardExhaustive && chkExhaustive) {
      cardExhaustive.classList.toggle("checked", chkExhaustive.checked);
    }
  }

  if (cardSummary && chkSummary) {
    cardSummary.addEventListener("click", (e) => {
      if (e.target !== chkSummary) {
        chkSummary.checked = !chkSummary.checked;
      }
      updateOptionCards();
    });
    chkSummary.addEventListener("change", updateOptionCards);
  }

  if (cardExhaustive && chkExhaustive) {
    cardExhaustive.addEventListener("click", (e) => {
      if (e.target !== chkExhaustive) {
        chkExhaustive.checked = !chkExhaustive.checked;
      }
      updateOptionCards();
    });
    chkExhaustive.addEventListener("change", updateOptionCards);
  }

  // --- File Upload & Drag/Drop Handlers ---
  if (btnChooseFile) {
    btnChooseFile.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.click();
    });
  }

  dropZone.addEventListener("click", () => fileInput.click());

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  });

  removeFileBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    resetFile();
  });

  function handleFileSelected(file) {
    hideAlert();
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (![".pdf", ".docx"].includes(ext)) {
      showAlert("Invalid File Type", "Please upload a valid PDF or DOCX file.");
      return;
    }

    selectedFile = file;
    fileNameDisplay.textContent = file.name;
    fileMetaDisplay.textContent = formatBytes(file.size);
    fileCardIcon.textContent = ext.replace(".", "").toUpperCase();
    if (fileStatusLabel) {
      fileStatusLabel.textContent = file.name;
    }

    dropZonePrompt.classList.add("hidden");
    fileCard.classList.remove("hidden");
    btnSummarize.disabled = false;
  }

  function resetFile() {
    selectedFile = null;
    fileInput.value = "";
    if (fileStatusLabel) {
      fileStatusLabel.textContent = "No file chosen";
    }
    dropZonePrompt.classList.remove("hidden");
    fileCard.classList.add("hidden");
    btnSummarize.disabled = true;
    hideAlert();
  }

  // --- Generate Action (Mandatory: Upload + Summary/Exhaustive) ---
  btnSummarize.addEventListener("click", async () => {
    if (!selectedFile) {
      showAlert("Document Required", "Please choose a document (PDF) to analyze.");
      return;
    }

    const wantSummary = chkSummary ? chkSummary.checked : true;
    const wantExhaustive = chkExhaustive ? chkExhaustive.checked : true;

    if (!wantSummary && !wantExhaustive) {
      showAlert("Setting Required", "Please select at least one format: Generate Summary or Generate Exhaustive Notes.");
      return;
    }

    hideAlert();

    // Switch view to Preview Notes tab
    switchToTab("preview");
    setLoading(true);

    const formData = new FormData();
    formData.append("file", selectedFile);

    const chapterVal = manualChapterInput ? manualChapterInput.value.trim() : "";
    if (chapterVal) {
      formData.append("chapters", chapterVal);
    }

    try {
      updateLoadingStage("Extracting Document Text...", "Reading and analyzing text faithfully with Zero Hallucination.");

      const response = await fetch("/api/v1/notes/summarize", {
        method: "POST",
        body: formData,
      });

      const result = await response.json();

      if (!response.ok || !result.success) {
        const errorMsg =
          result?.error?.message ||
          result?.detail?.message ||
          result?.detail ||
          "Failed to generate notes.";
        throw new Error(errorMsg);
      }

      displayResults(result, wantSummary, wantExhaustive);
    } catch (err) {
      console.error(err);
      showAlert("Generation Failed", err.message || "An unexpected error occurred.");
      setLoading(false, false);
      switchToTab("config");
    }
  });

  function displayResults(data, wantSummary = true, wantExhaustive = true) {
    let finalMarkdown = data.summary || "";

    // If only Summary or only Exhaustive Notes is requested, filter sections if appropriate
    if (wantSummary && !wantExhaustive) {
      if (previewCardTitle) previewCardTitle.textContent = "High-Level Academic Summary";
      // Extract Executive Summary section if present
      const summaryMatch = finalMarkdown.match(/##\s*📌?\s*Executive Summary([\s\S]*?)(?=##|$)/i);
      if (summaryMatch && summaryMatch[1].trim()) {
        finalMarkdown = `# 📚 High-Level Academic Summary\n\n## 📌 Executive Summary\n${summaryMatch[1].trim()}`;
      }
    } else if (!wantSummary && wantExhaustive) {
      if (previewCardTitle) previewCardTitle.textContent = "Exhaustive Deep-Dive Study Notes";
      // Remove Executive Summary section and keep detailed notes
      finalMarkdown = finalMarkdown.replace(/##\s*📌?\s*Executive Summary[\s\S]*?(?=##\s*🔑|##\s*📋|$)/i, "");
    } else {
      if (previewCardTitle) previewCardTitle.textContent = "Structured Summary & Exhaustive Notes";
    }

    currentRawMarkdown = finalMarkdown;
    setLoading(false, true);

    // Render markdown with Marked.js
    markdownOutput.innerHTML = marked.parse(finalMarkdown);

    // Populate clean metadata
    const meta = data.metadata || {};
    metaFilename.textContent = meta.filename || selectedFile?.name || "-";
    metaWords.textContent = (meta.processed_words || 0).toLocaleString();
    
    if (meta.is_full_document) {
      metaScope.textContent = "All Chapters (Full Document)";
    } else {
      const reqList = meta.chapters_requested || meta.chapters_found || [];
      const numOnly = reqList
        .map(c => String(c).replace(/^(chapter|ch\.|section|sec\.)\s*/i, "").split(/[:\-–—]/)[0].trim())
        .filter(Boolean);
      metaScope.textContent = numOnly.length > 0 ? `Chapter ${numOnly.join(", ")}` : "Specific Chapters";
    }
  }

  function setLoading(isLoading, hasData = false) {
    if (isLoading) {
      emptyState.classList.add("hidden");
      notesResult.classList.add("hidden");
      outputActions.classList.add("hidden");
      loadingState.classList.remove("hidden");
      btnSummarize.disabled = true;
    } else {
      loadingState.classList.add("hidden");
      btnSummarize.disabled = !selectedFile;
      if (hasData) {
        notesResult.classList.remove("hidden");
        outputActions.classList.remove("hidden");
        emptyState.classList.add("hidden");
      } else {
        emptyState.classList.remove("hidden");
        notesResult.classList.add("hidden");
        outputActions.classList.add("hidden");
      }
    }
  }

  function updateLoadingStage(title, desc) {
    loadingStageTitle.textContent = title;
    loadingStageDesc.textContent = desc;
  }

  // --- Copy, Markdown Download, and PDF Export ---
  btnCopy.addEventListener("click", () => {
    if (!currentRawMarkdown) return;
    navigator.clipboard.writeText(currentRawMarkdown).then(() => {
      showToast("Notes copied to clipboard!");
    });
  });

  // --- Print Header Helper ---
  function preparePdfHeader() {
    const docName = selectedFile ? selectedFile.name.replace(/\.[^/.]+$/, "") : "Document";
    const pdfDocTitle = document.getElementById("pdfDocTitle");
    const pdfDocMeta = document.getElementById("pdfDocMeta");
    if (pdfDocTitle) pdfDocTitle.textContent = `${docName} - Study Notes`;
    if (pdfDocMeta) {
      pdfDocMeta.textContent = `Document: ${docName} | Scope: ${metaScope.textContent || "Full Document"} | Total Words: ${metaWords.textContent || "-"} | NoteMaker AI`;
    }
  }

  // --- Print Button: Opens Browser Native Print / Save-as-PDF ---
  const btnPrint = document.getElementById("btnPrint");
  if (btnPrint) {
    btnPrint.addEventListener("click", () => {
      if (!markdownOutput.innerHTML) return;
      preparePdfHeader();
      window.print();
    });
  }

  // --- Export PDF Button ---
  btnPdf.addEventListener("click", async () => {
    if (!markdownOutput.innerHTML) return;

    const docName = selectedFile ? selectedFile.name.replace(/\.[^/.]+$/, "") : "document";
    const originalBtnText = btnPdf.innerHTML;

    btnPdf.disabled = true;
    btnPdf.innerHTML = `<span>⏳ Exporting PDF...</span>`;
    showToast("Generating PDF notes...");

    const printableWrapper = document.getElementById("printableWrapper") || markdownOutput;
    const pdfHeader = document.getElementById("pdfHeader");

    try {
      preparePdfHeader();
      if (pdfHeader) pdfHeader.classList.remove("hidden");

      // Give browser brief tick to paint header before snapshot
      await new Promise(r => setTimeout(r, 60));

      const opt = {
        margin:       [12, 12, 14, 12],
        filename:     `${docName}_notes.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  {
          scale: 2,
          useCORS: true,
          logging: false,
          backgroundColor: '#ffffff'
        },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak:    { mode: ['avoid-all', 'css', 'legacy'] }
      };

      await html2pdf().set(opt).from(printableWrapper).save();
      showToast("PDF downloaded successfully!");
    } catch (clientErr) {
      console.error("PDF generation encountered an error:", clientErr);
      showToast("Opening print dialog as fallback...");
      window.print();
    } finally {
      if (pdfHeader) pdfHeader.classList.add("hidden");
      btnPdf.disabled = false;
      btnPdf.innerHTML = originalBtnText;
    }
  });

  // --- Helpers ---
  function showAlert(title, message) {
    let cleanMsg = String(message || "An unexpected error occurred.");
    if (cleanMsg.includes("Available detected chapters")) {
      cleanMsg = cleanMsg.split("Available detected chapters")[0].trim();
    }
    alertTitle.textContent = title;
    alertMessage.textContent = cleanMsg;
    alertBox.classList.remove("hidden");
  }

  function hideAlert() {
    alertBox.classList.add("hidden");
  }

  function showToast(text) {
    toast.textContent = text;
    toast.classList.remove("hidden");
    setTimeout(() => {
      toast.classList.add("hidden");
    }, 2800);
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }
});
