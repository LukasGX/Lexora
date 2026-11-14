// search
const paragraphs = document.querySelectorAll(".paragraph");
const resultsLabel = document.querySelector("#search-results");
const searchInput = document.querySelector("#law-search");

if (searchInput) {
	const paragraphs = document.querySelectorAll(".paragraph");
	const resultsLabel = document.querySelector("#search-results");

	searchInput.addEventListener("input", () => {
		const query = searchInput.value.trim().toLowerCase();

		let count = 0;

		paragraphs.forEach((paragraph) => {
			const searchData = paragraph.dataset.search.toLowerCase();
			const matches = searchData.includes(query);

			paragraph.hidden = !matches;

			if (matches) count++;
		});

		if (resultsLabel) {
			resultsLabel.textContent = query ? `${count} Treffer` : "";
		}
	});
}

document.addEventListener("keydown", (event) => {
	if (
		event.key === "/" &&
		!["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)
	) {
		event.preventDefault();
		searchInput.focus();
	}

	if (event.key === "Escape" && document.activeElement === searchInput) {
		searchInput.value = "";
		searchInput.dispatchEvent(new Event("input"));
		searchInput.blur();
	}
});

// responsive
const toggle = document.getElementById("nav-toggle");
const nav = document.querySelector("aside.nav");

toggle.addEventListener("click", () => {
	const open = nav.classList.toggle("open");

	toggle.innerHTML = open
		? '<i class="fa-solid fa-xmark"></i>'
		: '<i class="fa-solid fa-bars"></i>';

	toggle.setAttribute("aria-expanded", open);
});
