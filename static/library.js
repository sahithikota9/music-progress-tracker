async function loadLibrary(mode) {
    const response = await fetch(`/get_library?mode=${mode}`);
    const files = await response.json();

    const container = document.getElementById(
        mode === "public" ? "musicContainer" : "manageContainer"
    );
    container.innerHTML = "";

    files.forEach(file => {
        const card = document.createElement("div");
        card.className = "card";

        card.innerHTML = `
            <h3>${file.name}</h3>
            <p class="category">${file.category}</p>
            <audio controls src="/static/${file.path}"></audio>
            ${mode === "private" ? `
                <button onclick="deleteFile('${file.path}')">Delete</button>
            ` : ""}
        `;

        container.appendChild(card);
    });
}

// ========== UPLOAD FILE (PRIVATE ONLY) ==========
async function uploadFile() {
    const file = document.getElementById("fileInput").files[0];
    const category = document.getElementById("uploadCategory").value;
    const makePublic = document.getElementById("makePublic").checked;

    if (!file) return alert("Please select a file.");

    const form = new FormData();
    form.append("file", file);
    form.append("category", category);
    form.append("public", makePublic);

    const response = await fetch("/upload_audio", {
        method: "POST",
        body: form
    });

    if (response.ok) {
        alert("Uploaded!");
        loadLibrary("private");
    } else {
        alert("Failed to upload");
    }
}

// ========== DELETE FILE (PRIVATE ONLY) ==========
async function deleteFile(path) {
    const confirmDelete = confirm("Delete this file?");
    if (!confirmDelete) return;

    const response = await fetch("/delete_audio", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ path })
    });

    if (response.ok) {
        loadLibrary("private");
    } else {
        alert("Delete failed");
    }
}
