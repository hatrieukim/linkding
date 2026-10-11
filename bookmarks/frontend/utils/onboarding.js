// Pure helpers for the onboarding practice area. They are kept free of DOM
// access so that they are easy to reason about and to test.

/**
 * Turns whatever the user typed into an absolute http(s) URL, or returns null
 * if it does not look like a link.
 */
export function normalizeUrl(input) {
  const value = (input || "").trim();
  if (!value || /\s/.test(value)) {
    return null;
  }
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(value)
    ? value
    : `https://${value}`;
  try {
    const url = new URL(withScheme);
    const isHttp = url.protocol === "http:" || url.protocol === "https:";
    if (!isHttp || !url.hostname.includes(".")) {
      return null;
    }
    return url.href;
  } catch (e) {
    return null;
  }
}

/**
 * Builds a readable placeholder title for a practice bookmark from its URL.
 */
export function titleFromUrl(href) {
  try {
    const url = new URL(href);
    const host = url.hostname.replace(/^www\./, "");
    const lastSegment = url.pathname.split("/").filter(Boolean).pop();
    if (!lastSegment) {
      return host;
    }
    const readable = decodeURIComponent(lastSegment)
      .replace(/\.[a-z0-9]{2,5}$/i, "")
      .replace(/[-_+]+/g, " ")
      .trim();
    return readable || host;
  } catch (e) {
    return href;
  }
}

/**
 * Tags are single words: lower case, no leading #, no spaces, no commas.
 */
export function normalizeTag(input) {
  return (input || "")
    .trim()
    .replace(/^#+/, "")
    .replace(/[\s,]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
}

/**
 * Lower-cases and strips Vietnamese diacritics so that "doc sau" finds "đọc-sau".
 */
export function fold(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/gi, "d")
    .toLowerCase();
}

/**
 * Returns the bookmarks whose title, URL or tags contain every word of the query.
 */
export function filterBookmarks(bookmarks, query) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return bookmarks;
  }
  return bookmarks.filter((bookmark) => {
    const haystack = fold(
      [bookmark.title, bookmark.url, ...bookmark.tags].join(" "),
    );
    return words.every((word) => haystack.includes(word));
  });
}
