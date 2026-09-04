import type { PendingCapture, PendingImageCapture } from "./lib/types";

const MENU_ID = "nemo-anki-add-selection";
const IMAGE_MENU_ID = "nemo-anki-add-image";
const PROPOSAL_WINDOW_WIDTH = 420;
const PROPOSAL_WINDOW_HEIGHT = 600;

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Add to Nemo Anki",
    contexts: ["selection"],
  });
  chrome.contextMenus.create({
    id: IMAGE_MENU_ID,
    title: "Add image to Nemo Anki",
    contexts: ["image"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === IMAGE_MENU_ID) {
    if (!info.srcUrl) return;
    void openImageProposalWindow(info.srcUrl, tab);
    return;
  }
  if (info.menuItemId !== MENU_ID) return;
  const text = (info.selectionText ?? "").trim();
  if (!text) return;
  void openProposalWindow(text, tab);
});

// No persistent content script: the keyboard shortcut instead does a one-off
// injection (activeTab-scoped, runs only on this explicit user gesture) to read
// the current selection, then discards itself — same zero-footprint approach as
// the context menu, just for the trigger that doesn't hand us the text directly.
chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command !== "capture-selection" || !tab?.id) return;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection()?.toString() ?? "",
    });
    const text = (results[0]?.result ?? "").trim();
    if (!text) return;
    void openProposalWindow(text, tab);
  } catch {
    // Restricted page (chrome://, the Web Store, etc.) — nothing we can do.
  }
});

async function openProposalWindow(text: string, tab?: chrome.tabs.Tab): Promise<void> {
  const capture: PendingCapture = {
    id: crypto.randomUUID(),
    text,
    sourceUrl: tab?.url ?? "",
    sourceTitle: tab?.title ?? "",
    createdAt: Date.now(),
  };
  await chrome.storage.session.set({ [`capture:${capture.id}`]: capture });

  await chrome.windows.create({
    url: chrome.runtime.getURL(`proposal.html?capture=${capture.id}`),
    type: "popup",
    width: PROPOSAL_WINDOW_WIDTH,
    height: PROPOSAL_WINDOW_HEIGHT,
  });
}

async function openImageProposalWindow(imageUrl: string, tab?: chrome.tabs.Tab): Promise<void> {
  const capture: PendingImageCapture = {
    id: crypto.randomUUID(),
    imageUrl,
    sourceUrl: tab?.url ?? "",
    sourceTitle: tab?.title ?? "",
    createdAt: Date.now(),
  };
  await chrome.storage.session.set({ [`image:${capture.id}`]: capture });

  await chrome.windows.create({
    url: chrome.runtime.getURL(`proposal.html?image=${capture.id}`),
    type: "popup",
    width: PROPOSAL_WINDOW_WIDTH,
    height: PROPOSAL_WINDOW_HEIGHT,
  });
}
