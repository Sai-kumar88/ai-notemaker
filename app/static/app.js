// NoteMaker AI Frontend Logic
document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const dropZonePrompt = document.getElementById("dropZonePrompt");
  const fileCard = document.getElementById("fileCard");
  const fileNameDisplay = document.getElementById("fileNameDisplay");
  const fileMetaDisplay = document.getElementById("fileMetaDisplay");
  const fileCardIcon = document.getElementById("fileCardIcon");
  const removeFileBtn = document.getElementById("removeFileBtn");

  const tabFullDoc = document.getElementById("tabFullDoc");
  const tabChapters = document.getElementById("tabChapters");
  const chaptersContainer = document.getElementById("chaptersContainer");
  const manualChapterInput = document.getElementById("manualChapterInput");

  const btnSummarize = document.getElementById("btnSummarize");
  const alertBox = document.getElementById("alertBox");
  const alertTitle = document.getElementById("alertTitle");
  const alertMessage = document.getElementById("alertMessage");

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
  const btnDownload = document.getElementById("btnDownload");
  const btnPdf = document.getElementById("btnPdf");
  const toast = document.getElementById("toast");

  // State
  let selectedFile = null;
  let currentRawMarkdown = "";
  let currentScope = "full"; // "full" or "chapters"

  // --- Drag & Drop Handlers ---
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

    dropZonePrompt.classList.add("hidden");
    fileCard.classList.remove("hidden");
    btnSummarize.disabled = false;
  }

  function resetFile() {
    selectedFile = null;
    fileInput.value = "";
    dropZonePrompt.classList.remove("hidden");
    fileCard.classList.add("hidden");
    btnSummarize.disabled = true;
    manualChapterInput.value = "";
    hideAlert();
  }

  // --- Scope Selection ---
  tabFullDoc.addEventListener("click", () => {
    currentScope = "full";
    tabFullDoc.classList.add("active");
    tabChapters.classList.remove("active");
    chaptersContainer.classList.add("hidden");
    manualChapterInput.value = "";
  });

  tabChapters.addEventListener("click", () => {
    currentScope = "chapters";
    tabChapters.classList.add("active");
    tabFullDoc.classList.remove("active");
    chaptersContainer.classList.remove("hidden");
    manualChapterInput.focus();
  });

  // --- Summarization Action ---
  btnSummarize.addEventListener("click", async () => {
    if (!selectedFile) return;

    hideAlert();
    setLoading(true);

    const formData = new FormData();
    formData.append("file", selectedFile);

    // If scope is specific chapters and user typed chapter numbers, pass them
    if (currentScope === "chapters") {
      const chapterVal = manualChapterInput.value.trim();
      if (chapterVal) {
        formData.append("chapters", chapterVal);
      }
      // If user selected specific chapters tab but left it blank, it omits 'chapters'
      // and automatically summarizes all chapters!
    }
    // If currentScope === 'full', chapters parameter is completely omitted

    try {
      updateLoadingStage("Extracting Document Text...", "Reading and analyzing text faithfully.");

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
          "Failed to generate summary.";
        throw new Error(errorMsg);
      }

      displayResults(result);
    } catch (err) {
      console.error(err);
      showAlert("Summarization Failed", err.message || "An unexpected error occurred.");
      setLoading(false, false);
    }
  });

  function displayResults(data) {
    currentRawMarkdown = data.summary;
    setLoading(false, true);

    // Render markdown with Marked.js
    markdownOutput.innerHTML = marked.parse(data.summary);

    // Populate clean metadata
    const meta = data.metadata || {};
    metaFilename.textContent = meta.filename || "-";
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

  btnDownload.addEventListener("click", () => {
    if (!currentRawMarkdown) return;
    const blob = new Blob([currentRawMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const docName = selectedFile ? selectedFile.name.replace(/\.[^/.]+$/, "") : "document";
    a.href = url;
    a.download = `${docName}_notes.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("Downloaded as Markdown!");
  });

  // --- Helper: Build Pre-Paginated PDF Document to Prevent Sentence Slicing ---
  function buildPaginatedPdfDocument(sourceHtml, docTitle, scopeText, wordsText) {
    // 1. Temporary measurement staging container in DOM
    const staging = document.createElement("div");
    staging.className = "pdf-export-container";
    staging.style.cssText = "position:absolute; left:-9999px; top:0; width:720px; padding:24px 28px; box-sizing:border-box; background:#ffffff; font-size:13px; line-height:1.55;";

    const formattedDate = new Date().toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric"
    });

    // Build Header
    const headerNode = document.createElement("div");
    headerNode.className = "pdf-header";
    headerNode.innerHTML = `
      <h1>AI NOTE MAKER STUDY NOTES</h1>
    `;
    staging.appendChild(headerNode);

    // 2. Parse markdown HTML and unwrap any nested lists into standalone .pdf-item blocks
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = sourceHtml;

    const flattenedItems = [];

    Array.from(tempDiv.children).forEach(child => {
      const tag = child.tagName.toLowerCase();

      if (tag === "ul" || tag === "ol") {
        // Break out each <li> into a standalone block so html2pdf never cuts inside a tall list
        Array.from(child.children).forEach((li, idx) => {
          const item = document.createElement("div");
          item.className = "pdf-item pdf-li";
          const bullet = tag === "ol" ? `${idx + 1}.` : "•";
          item.innerHTML = `<span class="pdf-bullet">${bullet}</span><div class="pdf-li-content">${li.innerHTML}</div>`;
          flattenedItems.push(item);
          staging.appendChild(item);
        });
      } else if (["h1", "h2", "h3", "h4"].includes(tag)) {
        const item = document.createElement("div");
        item.className = `pdf-item pdf-heading pdf-${tag}`;
        item.innerHTML = child.innerHTML;
        flattenedItems.push(item);
        staging.appendChild(item);
      } else {
        const item = document.createElement("div");
        item.className = `pdf-item pdf-${tag}`;
        item.innerHTML = child.innerHTML;
        flattenedItems.push(item);
        staging.appendChild(item);
      }
    });

    document.body.appendChild(staging);

    // 3. Measure heights and insert explicit .html2pdf__page-break elements
    // A4 printable height budget at 720px width = ~960px safe height per page
    const PAGE_HEIGHT_BUDGET = 950;
    let currentHeight = headerNode.offsetHeight || 60;

    const finalContainer = document.createElement("div");
    finalContainer.className = "pdf-export-container";
    finalContainer.style.cssText = "width:720px; padding:24px 28px; box-sizing:border-box; background:#ffffff; font-size:13px; line-height:1.55;";
    finalContainer.appendChild(headerNode.cloneNode(true));

    flattenedItems.forEach(item => {
      const itemHeight = Math.max(item.offsetHeight, 24);
      const isHeading = item.classList.contains("pdf-heading");

      // Check if adding this item overflows the current page
      // Also prevent leaving orphan headings near the bottom (within 100px of page bottom)
      const wouldOverflow = (currentHeight + itemHeight > PAGE_HEIGHT_BUDGET);
      const headingNearBottom = isHeading && (currentHeight + itemHeight + 100 > PAGE_HEIGHT_BUDGET);

      if (wouldOverflow || headingNearBottom) {
        const breakElem = document.createElement("div");
        breakElem.className = "html2pdf__page-break";
        finalContainer.appendChild(breakElem);
        currentHeight = itemHeight;
      } else {
        currentHeight += itemHeight;
      }

      finalContainer.appendChild(item.cloneNode(true));
    });

    // Clean up staging measurement container
    if (staging.parentNode) {
      staging.parentNode.removeChild(staging);
    }

    return finalContainer;
  }

  btnPdf.addEventListener("click", async () => {
    if (!markdownOutput.innerHTML) return;

    const docName = selectedFile ? selectedFile.name.replace(/\.[^/.]+$/, "") : "document";
    const originalBtnText = btnPdf.innerHTML;

    btnPdf.disabled = true;
    btnPdf.innerHTML = `<span>⏳ Generating PDF...</span>`;
    showToast("Generating high-quality PDF...");

    try {
      // 1. Primary: High-fidelity Server-side Vector PDF via PyMuPDF (Zero broken sentences)
      const response = await fetch("/api/v1/notes/export-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          html: markdownOutput.innerHTML,
          title: selectedFile ? selectedFile.name.replace(/\.[^/.]+$/, "") : "Document",
          scope: metaScope.textContent || "Full Document",
          word_count: metaWords.textContent || null
        })
      });

      if (response.ok) {
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        const downloadLink = document.createElement("a");
        downloadLink.href = blobUrl;
        downloadLink.download = "AI STUDY NOTES & GUIDE.pdf";
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
        URL.revokeObjectURL(blobUrl);
        showToast("PDF downloaded successfully!");
        btnPdf.disabled = false;
        btnPdf.innerHTML = originalBtnText;
        return;
      }
      throw new Error(`Server returned status ${response.status}`);
    } catch (serverErr) {
      console.warn("Server PDF export unavailable, trying client-side fallback:", serverErr);

      // 2. Client-side Fallback using Pre-paginated container
      try {
        const printableElement = buildPaginatedPdfDocument(
          markdownOutput.innerHTML,
          "AI STUDY NOTES & GUIDE",
          metaScope.textContent || "Full Document",
          metaWords.textContent || "-"
        );

        printableElement.style.position = "fixed";
        printableElement.style.left = "-9999px";
        printableElement.style.top = "0";
        printableElement.style.zIndex = "-999";
        document.body.appendChild(printableElement);

        const opt = {
          margin:       [12, 12, 14, 12],
          filename:     "AI STUDY NOTES & GUIDE.pdf",
          image:        { type: 'jpeg', quality: 0.98 },
          html2canvas:  {
            scale: 2,
            useCORS: true,
            letterRendering: true,
            scrollY: 0,
            scrollX: 0,
            windowWidth: 720
          },
          jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' },
          pagebreak:    { mode: ['legacy'] }
        };

        await html2pdf().set(opt).from(printableElement).save();
        showToast("PDF downloaded successfully!");
        if (printableElement.parentNode) {
          printableElement.parentNode.removeChild(printableElement);
        }
      } catch (clientErr) {
        console.error("Client PDF generation also failed:", clientErr);
        showToast("Opening browser print dialog...");
        window.print();
      } finally {
        btnPdf.disabled = false;
        btnPdf.innerHTML = originalBtnText;
      }
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
