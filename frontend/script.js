let fullLibrary = [];
let targetResults = [];

// F19: XSS escaping helper for innerHTML injection
const esc = (s) => {
    if (!s) return "";
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
};

document.addEventListener('DOMContentLoaded', () => {
    // Helper to fetch and build the library datalist
    const loadLibrary = () => {
        fetch('/api/library')
            .then(res => res.json())
            .then(data => {
                fullLibrary = data.library || [];
                
                let dataList = document.getElementById('library-datalist');
                if (!dataList) {
                    dataList = document.createElement('datalist');
                    dataList.id = 'library-datalist';
                    document.body.appendChild(dataList);
                }
                
                dataList.innerHTML = ''; // Clear existing
                fullLibrary.forEach(song => {
                    const opt = document.createElement('option');
                    opt.value = song;
                    dataList.appendChild(opt);
                });
                if (fullLibrary.length === 0) {
                    const status = document.getElementById('status');
                    if (status.innerText === "Ready." || status.innerText.startsWith("⚠️")) {
                        status.innerText = "⚠️ No library loaded. Please import an M3U backup from the dropdown above to get started.";
                        status.style.color = "var(--accent)";
                    }
                } else {
                    const status = document.getElementById('status');
                    if (status.innerText.startsWith("⚠️")) {
                         status.innerText = "Ready.";
                         status.style.color = "";
                    }
                }
            })
            .catch(err => console.error("Error fetching library:", err));
    };

    // Helper to fetch and populate available M3U files in the root folder
    const loadM3uFiles = () => {
        fetch('/api/list_m3u_files')
            .then(res => res.json())
            .then(data => {
                const select = document.getElementById('m3uInput');
                const m3uFiles = data.m3u_files || [];
                
                select.innerHTML = ''; // Clear default
                
                if (m3uFiles.length === 0) {
                    const opt = document.createElement('option');
                    opt.value = "";
                    opt.disabled = true;
                    opt.selected = true;
                    opt.textContent = "No M3U files found in project folder";
                    select.appendChild(opt);
                } else {
                    const defaultOpt = document.createElement('option');
                    defaultOpt.value = "";
                    defaultOpt.disabled = true;
                    defaultOpt.selected = true;
                    defaultOpt.textContent = `Select an M3U Backup... (${m3uFiles.length} found)`;
                    select.appendChild(defaultOpt);
                    
                    m3uFiles.forEach(file => {
                        const opt = document.createElement('option');
                        opt.value = file.path;
                        opt.textContent = `📄 ${file.name}`;
                        select.appendChild(opt);
                    });
                }
            })
            .catch(err => console.error("Error fetching M3U files:", err));
    };

    // Fetch full library on load for dropdowns
    loadLibrary();
    loadM3uFiles();

    // --- CROP SETTINGS UI LOGIC ---
    const cropModeSelect = document.getElementById('cropModeSelect');
    const customCropInputs = document.getElementById('customCropInputs');
    if (cropModeSelect && customCropInputs) {
        cropModeSelect.addEventListener('change', () => {
            if (cropModeSelect.value === 'custom') {
                customCropInputs.classList.remove('hidden');
            } else {
                customCropInputs.classList.add('hidden');
            }
        });
    }

    // --- IMPORT M3U LIBRARY ---
    const importM3uBtn = document.getElementById('importM3uBtn');
    importM3uBtn.addEventListener('click', async () => {
        const m3uPath = document.getElementById('m3uInput').value;
        const status = document.getElementById('status');
        
        if(!m3uPath) {
            status.innerText = "Please enter an M3U file path to import.";
            return;
        }

        const confirmOverwrite = confirm("WARNING: Importing an M3U backup will overwrite your existing songs_full_info.csv database.\n\nAre you sure you want to reconstruct the library?");
        if (!confirmOverwrite) {
            return;
        }
        
        status.innerText = "Importing M3U and rebuilding database... please wait.";
        importM3uBtn.disabled = true;

        try {
            const res = await fetch('/api/import_m3u', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ m3u_path: m3uPath })
            });

            const data = await res.json();
            
            if(res.ok) {
                status.innerText = `Library rebuilt! ${data.count} songs loaded from M3U.`;
                loadLibrary();
                // Refresh and reset dropdown AFTER new content loads
                fetch('/api/list_m3u_files')
                    .then(res => res.json())
                    .then(data => {
                        const select = document.getElementById('m3uInput');
                        select.innerHTML = '';
                        const defaultOpt = document.createElement('option');
                        defaultOpt.value = "";
                        defaultOpt.disabled = true;
                        defaultOpt.selected = true;
                        defaultOpt.textContent = `Select an M3U Backup... (${(data.m3u_files||[]).length} found)`;
                        select.appendChild(defaultOpt);
                        (data.m3u_files || []).forEach(file => {
                            const opt = document.createElement('option');
                            opt.value = file.path;
                            opt.textContent = `📄 ${file.name}`;
                            select.appendChild(opt);
                        });
                        // Reset is now safe — DOM is ready
                        select.value = '';
                    })
                    .catch(err => console.error("Error refreshing M3U list:", err));
            } else {

                status.innerText = "Error: " + (data.detail || "Unknown error");
            }
        } catch(e) {
            status.innerText = "Connection error during M3U import.";
            console.error(e);
        } finally {
            importM3uBtn.disabled = false;
        }
    });

    // --- SCAN FOLDER FOR TIMEFRAMES ---
    const scanBtn = document.getElementById('scanBtn');
    scanBtn.addEventListener('click', async () => {
        const folder = document.getElementById('folderInput').value.trim();
        const status = document.getElementById('status');
        const treeContainer = document.getElementById('treeContainer');
        const treeGrid = document.getElementById('treeGrid');
        
        if(!folder) {
            status.innerText = "Please enter a folder path.";
            return;
        }
        
        status.innerText = "Scanning full folder hierarchy... please wait.";
        scanBtn.disabled = true;
        treeContainer.classList.add('hidden');

        try {
            const res = await fetch('/api/scan_folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input_folder: folder })
            });

            const data = await res.json();
            
            if(res.ok) {
                status.innerText = "Scan complete. Select timeframes below.";
                renderTree(data.tree, treeGrid);
                treeContainer.classList.remove('hidden');
            } else {
                status.innerText = "Error: " + (data.detail || "Unknown error");
            }
        } catch(e) {
            status.innerText = "Connection error. Make sure backend is running.";
            console.error(e);
        } finally {
            scanBtn.disabled = false;
        }
    });

    // --- RUN PIPELINE ON SELECTED FILES ---
    const runSelectedBtn = document.getElementById('runSelectedBtn');
    runSelectedBtn.addEventListener('click', async () => {
        const status = document.getElementById('status');
        const anchorKeyword = document.getElementById('anchorInput').value.trim() || "Musicolet";
        
        const cropMode = document.getElementById('cropModeSelect').value;
        const useFullImage = (cropMode === 'full');
        let customCrop = null;
        if (cropMode === 'custom') {
            customCrop = [
                parseInt(document.getElementById('cropL').value) || 0,
                parseInt(document.getElementById('cropT').value) || 0,
                parseInt(document.getElementById('cropR').value) || 0,
                parseInt(document.getElementById('cropB').value) || 0
            ];
        }
        
        // Gather intelligently grouped files

        const selectedGroups = gatherCheckedGroups();
        
        if(Object.keys(selectedGroups).length === 0) {
            alert("Please check at least one timeframe to process.");
            return;
        }
        
        // Count total files for UI
        let totalFiles = 0;
        for(const files of Object.values(selectedGroups)) {
            totalFiles += files.length;
        }
        
        status.innerText = `Processing precisely ${totalFiles} file(s) across ${Object.keys(selectedGroups).length} group(s)...`;
        runSelectedBtn.disabled = true;

        try {
            const res = await fetch('/api/run_pipeline', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    groups: selectedGroups, 
                    anchor_keyword: anchorKeyword,
                    use_full_image: useFullImage,
                    crop_mode: cropMode,
                    custom_crop: customCrop
                })
            });

            const data = await res.json();
            
            if(res.ok) {
                targetResults = data.results; // Now a dict of groups
                status.innerText = `Successfully OCR processed ${totalFiles} images.`;
                renderResultsGrouped(targetResults, {
                    useFullImage,
                    cropMode,
                    customCrop
                });
            } else {

                status.innerText = "Error: " + (data.detail || "Unknown error");
            }
        } catch(e) {
            status.innerText = "Connection error processing files.";
            console.error(e);
        } finally {
            runSelectedBtn.disabled = false;
        }
    });

    const exportBtn = document.getElementById('exportBtn');
    exportBtn.addEventListener('click', async () => {
        // Collect all currently selected matches, grouped structurally
        const groupedMatches = {};
        
        const groupSections = document.querySelectorAll('.group-section');
        groupSections.forEach(section => {
            const groupName = section.dataset.group;
            const inputs = section.querySelectorAll('.song-input');
            const matches = Array.from(inputs).map(i => i.value).filter(v => v !== "");
            if (matches.length > 0) {
                groupedMatches[groupName] = matches;
            }
        });
        
        if(Object.keys(groupedMatches).length === 0) {
            alert("No songs to export.");
            return;
        }

        // F23: Prevent double-submission
        exportBtn.disabled = true;
        const originalText = exportBtn.innerText;
        exportBtn.innerText = "Exporting...";

        try {
            const res = await fetch('/api/generate_m3u', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ grouped_matches: groupedMatches })
            });
            const data = await res.json();
            if(res.ok) {
                alert(`Successfully exported ${data.count} individual M3U playlists to the output directory.`);
            } else {
                alert("Error: " + data.detail);
            }
        } catch(e) {
            console.error(e);
            alert("Connection error during export.");
        } finally {
            exportBtn.disabled = false;
            exportBtn.innerText = originalText;
        }
    });

    // --- SORT RESULTS (DOM-Based to preserve user edits) ---
    const sortSelect = document.getElementById('sortSelect');
    sortSelect.addEventListener('change', (e) => {
        const mode = e.target.value;
        const grids = document.querySelectorAll('.cards-grid');
        
        grids.forEach(grid => {
            const cards = Array.from(grid.querySelectorAll('.card'));
            cards.sort((a, b) => {
                const scoreA = parseFloat(a.dataset.score) || 0;
                const scoreB = parseFloat(b.dataset.score) || 0;
                // Combine date + time for cross-day accurate sorting
                const timeA = (a.dataset.date || "") + "T" + (a.dataset.time || "");
                const timeB = (b.dataset.date || "") + "T" + (b.dataset.time || "");

                if (mode === 'score_asc') {
                    // Lowest scores first to fix them
                    // Fallback to chronological if tied
                    return (scoreA - scoreB) || timeA.localeCompare(timeB);
                } else if (mode === 'score_desc') {
                    // Highest scores first
                    return (scoreB - scoreA) || timeA.localeCompare(timeB);
                } else { 
                    // Chronological
                    return timeA.localeCompare(timeB);
                }

            });
            // Re-append in the newly sorted order
            cards.forEach(c => grid.appendChild(c));
        });
    });
});

function renderResultsGrouped(groupedResults, cropSettings = {}) {
    const container = document.getElementById('resultsContainer');
    const cardsList = document.getElementById('cardsList');
    const countBadge = document.getElementById('countBadge');
    
    cardsList.innerHTML = '';
    
    let totalItems = 0;
    let autoId = 0;

    // Destructure crop settings for easy URL building
    const { useFullImage, cropMode, customCrop } = cropSettings;
    let cropQueryParams = `&use_full_image=${useFullImage}`;
    if (!useFullImage) {
        cropQueryParams += `&crop_mode=${cropMode}`;
        if (cropMode === 'custom' && customCrop) {
            cropQueryParams += `&l=${customCrop[0]}&t=${customCrop[1]}&r=${customCrop[2]}&b=${customCrop[3]}`;
        }
    }

    for (const [groupName, results] of Object.entries(groupedResults)) {

        if (results.length === 0) continue;
        
        totalItems += results.length;
        
        // Create Section Wrapper
        const section = document.createElement('div');
        section.className = 'group-section';
        section.dataset.group = groupName;
        section.style.marginBottom = "3rem";
        
        // Create Header
        const header = document.createElement('h3');
        // F19: Escaped groupName via innerHTML to avoid double-encoding
        header.innerHTML = `🗂️ ${esc(groupName)} (${results.length} songs)`;
        header.style.marginBottom = "1rem";
        header.style.paddingBottom = "0.5rem";
        header.style.borderBottom = "1px solid rgba(255,255,255,0.1)";
        section.appendChild(header);
        
        // Create Grid
        const grid = document.createElement('div');
        grid.className = 'cards-grid';
        
        results.forEach((item) => {
            const card = document.createElement('div');
            card.className = 'card';
            card.id = `card-${autoId}`;
            
            // Embed datasets for pure DOM-level sorting
            card.dataset.score = item.score;
            card.dataset.time = item.capture_time;
            card.dataset.date = item.date_object || "";   // "YYYY-MM-DD"

            
            // F19: Escaping all item properties
            const val = item.best_match ? esc(item.best_match) : "";
            const inputHtml = `<input type="text" list="library-datalist" id="input-${autoId}" class="song-input" value="${val}" placeholder="Type to search library..."/>`;

            card.innerHTML = `
                <div class="card-header">
                    <div>
                        <span class="time-badge">${esc(item.capture_time)}</span>
                        <span class="confidence" style="margin-left: 10px;">Score: ${Math.round(item.score)}</span>
                    </div>
                    <button class="btn-delete" onclick="document.getElementById('card-${autoId}').remove(); updateCountBadge();" title="Remove from M3U">X</button>
                </div>
                <div class="card-image" style="margin-top: 1rem; text-align: center;">
                    <img src="/api/image?path=${encodeURIComponent(item.filepath)}&processed=true${cropQueryParams}" alt="OCR Vision Preview" title="This is exactly what the Tesseract Engine sees" style="width: 100%; max-height: 200px; object-fit: contain; border-radius: 8px; border: 1px solid var(--accent); background: #000;">
                </div>

                <div class="card-content">
                    <p title="${esc(item.filepath)}"><strong>File:</strong> ${esc(item.filename)}</p>
                    <p><strong>Extracted:</strong> ${esc(item.extracted_text)}</p>
                    <label>Database Match:</label>
                    ${inputHtml}
                </div>
            `;
            
            grid.appendChild(card);
            autoId++;
        });
        
        section.appendChild(grid);
        cardsList.appendChild(section);
    }
    
    countBadge.innerText = `(${totalItems})`;
    container.classList.remove('hidden');
}

function updateCountBadge() {
    const remaining = document.querySelectorAll('.card').length;
    document.getElementById('countBadge').innerText = `(${remaining})`;
}

// --- TREE RENDERING LOGIC ---
function renderTree(treeData, container) {
    container.innerHTML = '';
    
    if (Object.keys(treeData).length === 0) {
        container.innerHTML = '<em>No valid screenshots found in timeframes.</em>';
        return;
    }

    const rootUl = document.createElement('div');
    rootUl.className = 'tree-root';

    for (const [year, months] of Object.entries(treeData)) {
        const yearNode = createTreeNode(year, 'year', months);
        rootUl.appendChild(yearNode);
    }
    
    container.appendChild(rootUl);
}

function createTreeNode(label, type, data, parentPath = "") {
    const node = document.createElement('div');
    node.className = 'tree-node';
    
    // Track explicit path for smart grouping (e.g., "2024_May_Week 19")
    const currentPath = parentPath ? `${parentPath}_${label}` : label;
    node.dataset.path = currentPath;
    node.dataset.type = type;
    
    const labelRow = document.createElement('label');
    labelRow.className = 'tree-label';
    
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    // This class lets us identify checkboxes we can explicitly read
    checkbox.className = 'tree-node-checkbox';
    
    const textSpan = document.createElement('span');
    textSpan.className = 'tree-text';
    textSpan.innerText = label;
    
    labelRow.appendChild(checkbox);
    labelRow.appendChild(textSpan);
    node.appendChild(labelRow);

    if (type === 'year' || type === 'month') {
        const childrenContainer = document.createElement('div');
        childrenContainer.className = 'tree-children';
        let totalFiles = 0;
        
        for (const [key, value] of Object.entries(data)) {
            const childType = type === 'year' ? 'month' : 'week';
            const childNode = createTreeNode(key, childType, value, currentPath);
            childrenContainer.appendChild(childNode);
            totalFiles += parseInt(childNode.dataset.count);
        }
        
        node.dataset.count = totalFiles;
        const countSpan = document.createElement('span');
        countSpan.className = 'tree-count';
        countSpan.innerText = totalFiles;
        labelRow.appendChild(countSpan);
        
        node.appendChild(childrenContainer);
        
        // Cascading checkbox logic
        checkbox.addEventListener('change', (e) => {
            const childCheckboxes = childrenContainer.querySelectorAll('input[type="checkbox"]');
            childCheckboxes.forEach(cb => cb.checked = e.target.checked);
        });
        
    } else if (type === 'week') {
        const files = data; // For week, data is the array of files
        node.dataset.count = files.length;
        
        const countSpan = document.createElement('span');
        countSpan.className = 'tree-count';
        countSpan.innerText = files.length;
        labelRow.appendChild(countSpan);
        
        // Store stringified filepaths for collection
        checkbox.dataset.files = JSON.stringify(files.map(f => f.filepath));
    }
    
    return node;
}

// --- ALGORITHM TO GATHER HIGHEST CHECKED NODES ---
function gatherCheckedGroups() {
    const groups = {};
    const root = document.querySelector('.tree-root');
    if(!root) return groups;
    
    function traverse(element) {
        // Iterate only over direct .tree-node children
        const children = element.children;
        for(let i=0; i<children.length; i++) {
            const child = children[i];
            if(child.classList.contains('tree-node')) {
                const checkbox = child.querySelector(':scope > .tree-label > input[type="checkbox"]');
                if(checkbox && checkbox.checked) {
                    // This node is explicitly checked!
                    // Gather all files under it, but DO NOT recurse deeper.
                    const groupName = child.dataset.path;
                    groups[groupName] = getAllFilesUnderNode(child);
                } else if (!checkbox.checked && child.dataset.type !== 'week') {
                    // Not checked, so maybe its children are explicitly checked. Recurse.
                    const container = child.querySelector(':scope > .tree-children');
                    if(container) traverse(container);
                }
            }
        }
    }
    
    traverse(root);
    return groups;
}

function getAllFilesUnderNode(node) {
    const files = [];
    if(node.dataset.type === 'week') {
        const checkbox = node.querySelector(':scope > .tree-label > input[type="checkbox"]');
        if(checkbox && checkbox.dataset.files) {
            files.push(...JSON.parse(checkbox.dataset.files));
        }
    } else {
        // If it's a year or month, find all week checkboxes inside its DOM
        const childWeekCheckboxes = node.querySelectorAll('.tree-children .tree-node[data-type="week"] > .tree-label > input[type="checkbox"]');
        childWeekCheckboxes.forEach(cb => {
            if(cb.dataset.files) {
                 files.push(...JSON.parse(cb.dataset.files));
            }
        });
    }
    return files;
}
