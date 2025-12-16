const API_URL = "https://tbi-backend-447216852170.us-central1.run.app";

let allData = [];
let sortKey = "created_utc";
let sortDir = "desc";

async function fetchReports() {
    const loading = document.getElementById("loading");
    const error = document.getElementById("error");
    const table = document.getElementById("data-table");
    
    loading.style.display = "block";
    error.style.display = "none";
    table.style.display = "none";
    
    try {
        const response = await fetch(`${API_URL}/reports`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        allData = await response.json();
        loading.style.display = "none";
        table.style.display = "table";
        updateRecordCount();
        renderTable();
    } catch (err) {
        loading.style.display = "none";
        error.style.display = "block";
        error.textContent = `Error loading data: ${err.message}`;
    }
}

function updateRecordCount() {
    const filtered = getFilteredData();
    const countEl = document.getElementById("record-count");
    countEl.textContent = `Showing ${filtered.length} of ${allData.length} records`;
}

function getFilteredData() {
    const search = document.getElementById("search").value.toLowerCase().trim();
    if (!search) return allData;
    return allData.filter(r => 
        (r.patient_name || "").toLowerCase().includes(search)
    );
}

function getSortValue(record, key) {
    if (key === "tests") {
        return [record.tests.vng, record.tests.ctsib, record.tests.creyos].filter(Boolean).length;
    }
    if (["pursuits", "saccades", "fixations", "eyeq", "standard_percentile", 
         "proprioception_percentile", "visual_percentile", "vestibular_percentile",
         "rpq", "pcl5", "psqi", "phq9", "gad7"].includes(key)) {
        return record.scores[key] ?? -1;
    }
    return record[key] || "";
}

function sortData(data) {
    return [...data].sort((a, b) => {
        let aVal = getSortValue(a, sortKey);
        let bVal = getSortValue(b, sortKey);
        
        if (typeof aVal === "string") aVal = aVal.toLowerCase();
        if (typeof bVal === "string") bVal = bVal.toLowerCase();
        
        if (aVal < bVal) return sortDir === "asc" ? -1 : 1;
        if (aVal > bVal) return sortDir === "asc" ? 1 : -1;
        return 0;
    });
}

function formatScore(val, type) {
    if (val === null || val === undefined) return "-";
    
    let className = "score-normal";
    if (type === "percentile") {
        if (val < 25) className = "score-low";
        else if (val < 50) className = "score-mid";
    } else if (type === "dysfunction") {
        if (val < 50) className = "score-low";
        else if (val < 75) className = "score-mid";
    } else if (type === "psy") {
        className = "";
    }
    
    return `<span class="${className}">${val}</span>`;
}

function formatDate(dateStr) {
    if (!dateStr) return "-";
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString();
    } catch {
        return dateStr;
    }
}

function renderTable() {
    const tbody = document.getElementById("table-body");
    const filtered = getFilteredData();
    const sorted = sortData(filtered);
    
    document.querySelectorAll("th").forEach(th => {
        th.classList.remove("sorted-asc", "sorted-desc");
        if (th.dataset.key === sortKey) {
            th.classList.add(sortDir === "asc" ? "sorted-asc" : "sorted-desc");
        }
    });
    
    tbody.innerHTML = sorted.map(r => {
        const tests = [];
        if (r.tests.vng) tests.push('<span class="test-badge test-vng">RightEye</span>');
        if (r.tests.ctsib) tests.push('<span class="test-badge test-ctsib">CTSIB</span>');
        if (r.tests.creyos) tests.push('<span class="test-badge test-creyos">Creyos</span>');
        
        return `<tr>
            <td>${r.patient_name || "-"}</td>
            <td>${r.dob || "-"}</td>
            <td>${r.doi || "-"}</td>
            <td>${tests.join("") || "-"}</td>
            <td class="score-cell">${formatScore(r.scores.pursuits, "dysfunction")}</td>
            <td class="score-cell">${formatScore(r.scores.saccades, "dysfunction")}</td>
            <td class="score-cell">${formatScore(r.scores.fixations, "dysfunction")}</td>
            <td class="score-cell">${formatScore(r.scores.eyeq, "dysfunction")}</td>
            <td class="score-cell">${formatScore(r.scores.standard_percentile, "percentile")}</td>
            <td class="score-cell">${formatScore(r.scores.proprioception_percentile, "percentile")}</td>
            <td class="score-cell">${formatScore(r.scores.visual_percentile, "percentile")}</td>
            <td class="score-cell">${formatScore(r.scores.vestibular_percentile, "percentile")}</td>
            <td class="score-cell">${formatScore(r.scores.rpq, "psy")}</td>
            <td class="score-cell">${formatScore(r.scores.pcl5, "psy")}</td>
            <td class="score-cell">${formatScore(r.scores.psqi, "psy")}</td>
            <td class="score-cell">${formatScore(r.scores.phq9, "psy")}</td>
            <td class="score-cell">${formatScore(r.scores.gad7, "psy")}</td>
            <td>${formatDate(r.created_utc)}</td>
        </tr>`;
    }).join("");
    
    updateRecordCount();
}

function exportToCSV() {
    const filtered = getFilteredData();
    const sorted = sortData(filtered);
    
    const headers = [
        "Patient Name", "DOB", "DOI", "RightEye", "CTSIB", "Creyos",
        "Pursuits", "Saccades", "Fixations", "EyeQ",
        "Standard %", "Proprioception %", "Visual %", "Vestibular %",
        "RPQ", "PCL-5", "PSQI", "PHQ-9", "GAD-7", "Created"
    ];
    
    const rows = sorted.map(r => [
        r.patient_name || "",
        r.dob || "",
        r.doi || "",
        r.tests.vng ? "Yes" : "No",
        r.tests.ctsib ? "Yes" : "No",
        r.tests.creyos ? "Yes" : "No",
        r.scores.pursuits ?? "",
        r.scores.saccades ?? "",
        r.scores.fixations ?? "",
        r.scores.eyeq ?? "",
        r.scores.standard_percentile ?? "",
        r.scores.proprioception_percentile ?? "",
        r.scores.visual_percentile ?? "",
        r.scores.vestibular_percentile ?? "",
        r.scores.rpq ?? "",
        r.scores.pcl5 ?? "",
        r.scores.psqi ?? "",
        r.scores.phq9 ?? "",
        r.scores.gad7 ?? "",
        r.created_utc || ""
    ]);
    
    const csvContent = [headers, ...rows]
        .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(","))
        .join("\n");
    
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `patient_data_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
}

document.querySelectorAll("th[data-key]").forEach(th => {
    th.addEventListener("click", () => {
        const key = th.dataset.key;
        if (sortKey === key) {
            sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
            sortKey = key;
            sortDir = "asc";
        }
        renderTable();
    });
});

document.getElementById("search").addEventListener("input", () => {
    renderTable();
});

document.getElementById("export-btn").addEventListener("click", exportToCSV);
document.getElementById("refresh-btn").addEventListener("click", fetchReports);

fetchReports();
