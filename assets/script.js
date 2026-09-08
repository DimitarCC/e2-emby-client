(function () {
  var header = document.querySelector(".site-header");
  var navToggle = document.querySelector(".nav-toggle");
  if (navToggle && header) {
    navToggle.addEventListener("click", function () {
      header.classList.toggle("open");
    });
  }

  var docsSide = document.querySelector(".docs-side");
  var docsToggle = document.querySelector(".docs-side-toggle");
  if (docsToggle && docsSide) {
    docsToggle.addEventListener("click", function () {
      docsSide.classList.toggle("open");
    });
  }

  // Highlight the current doc section link while scrolling.
  var sideLinks = document.querySelectorAll(".docs-side-inner a[href*=\"#\"]");
  var headings = [];
  sideLinks.forEach(function (link) {
    var id = link.getAttribute("href").split("#")[1];
    if (!id) return;
    var el = document.getElementById(id);
    if (el) headings.push({ el: el, link: link });
  });

  if (headings.length) {
    var onScroll = function () {
      var pos = window.scrollY + 100;
      var current = headings[0];
      headings.forEach(function (h) {
        if (h.el.offsetTop <= pos) current = h;
      });
      sideLinks.forEach(function (l) { l.classList.remove("active"); });
      current.link.classList.add("active");
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }
})();
