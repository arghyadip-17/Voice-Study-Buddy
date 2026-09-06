/*
  script.js
  ---------
  This file does four jobs:
    1. Turns the user's speech into text (browser SpeechRecognition = free STT).
    2. Sends that text to our backend (/api/ask), which returns an answer
       and Rime-generated audio.
    3. Plays that audio.
    4. Implements the CLIENT-SIDE HALF of the interruption/generation-id
       mechanism (the backend half lives in backend/main.py - read the big
       comment at the top of that file first, it explains the whole idea).

  THE CLIENT-SIDE GENERATION ID, IN PLAIN WORDS
  ----------------------------------------------
  `currentGenerationId` counts up every time the user starts a NEW question
  (a fresh question, or a question that interrupts the AI).

  When we get a response back from the server, we check:
      "Does this response's generation_id still match currentGenerationId?"
  If NOT, a newer question has started since this response was requested,
  so we throw the response away instead of playing stale audio - even if
  the server already sent it back successfully.

  This is a second, independent safety check on top of the server-side one,
  which makes it very unlikely that stale audio plays, even if the two
  checks race each other. It is not an absolute guarantee - see the note
  in backend/main.py's module docstring on why a check-then-act pattern
  like this can't fully rule out a rare race - but in practice this window
  is small and stale audio should be the rare exception, not the norm.
*/

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------
let currentGenerationId = 0;
let activeAbortController = null;
let interruptionCount = 0;

// ---------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------
const micBtn = document.getElementById("micBtn");
const interruptBtn = document.getElementById("interruptBtn");
const speakingIndicator = document.getElementById("speakingIndicator");
const listeningIndicator = document.getElementById("listeningIndicator");
const loadingIndicator = document.getElementById("loadingIndicator");
const conversation = document.getElementById("conversation");
const errorBox = document.getElementById("errorBox");
const audioPlayer = document.getElementById("audioPlayer");
const rimeStatusEl = document.getElementById("rimeStatus");
const interruptionCountEl = document.getElementById("interruptionCount");

// ---------------------------------------------------------------------
// Small UI helpers
// ---------------------------------------------------------------------
function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

function showError(message) {
  errorBox.textContent = message;
  show(errorBox);
  setTimeout(() => hide(errorBox), 6000);
}

function addBubble(text, who) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;
  div.textContent = text;
  conversation.appendChild(div);
  conversation.scrollTop = conversation.scrollHeight;
  return div;
}

function setInterruptionCount(n) {
  interruptionCount = n;
  interruptionCountEl.textContent = String(interruptionCount);
}

// ---------------------------------------------------------------------
// Check backend health on load (updates the "Rime Status" footer)
// ---------------------------------------------------------------------
async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (data.rime_key_set && data.llm_key_set) {
      rimeStatusEl.textContent = "● Active";
    } else {
      rimeStatusEl.textContent = "● Missing API key(s)";
    }
  } catch {
    rimeStatusEl.textContent = "● Offline";
  }
}
checkHealth();

// ---------------------------------------------------------------------
// Speech recognition (browser-native STT - see backend/stt.py for how to
// swap this for a server-side STT API later)
// ---------------------------------------------------------------------
const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;

function startListening() {
  if (!SpeechRecognitionAPI) {
    showError("Your browser doesn't support voice input. Try Chrome or Edge.");
    return;
  }

  hide(speakingIndicator);
  show(listeningIndicator);
  micBtn.disabled = true;

  const recognizer = new SpeechRecognitionAPI();
  recognizer.lang = "en-US";
  recognizer.interimResults = false;
  recognizer.maxAlternatives = 1;

  recognizer.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    hide(listeningIndicator);
    micBtn.disabled = false;
    addBubble(transcript, "user");
    askQuestion(transcript);
  };

  recognizer.onerror = (event) => {
    hide(listeningIndicator);
    micBtn.disabled = false;
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      showError("Microphone permission was denied. Please allow mic access and try again.");
    } else if (event.error === "no-speech") {
      showError("Didn't catch that - no speech detected. Try again.");
    } else {
      showError(`Speech recognition error: ${event.error}`);
    }
  };

  recognizer.onend = () => {
    hide(listeningIndicator);
    micBtn.disabled = false;
  };

  try {
    recognizer.start();
  } catch (err) {
    hide(listeningIndicator);
    micBtn.disabled = false;
    showError("Could not start the microphone. Please try again.");
  }
}

// ---------------------------------------------------------------------
// The core request/response flow, with the interruption-safe generation ID
// ---------------------------------------------------------------------
async function askQuestion(questionText) {
  if (!questionText || !questionText.trim()) {
    showError("I didn't hear a question - please try again.");
    return;
  }

  // Starting a new question always bumps the generation id. This alone is
  // enough to invalidate any older in-flight request once its response
  // comes back (see the check further down).
  currentGenerationId += 1;
  const myGenerationId = currentGenerationId;

  show(loadingIndicator);
  show(interruptBtn);

  const controller = new AbortController();
  activeAbortController = controller;

  let response;
  try {
    response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: questionText, generation_id: myGenerationId }),
      signal: controller.signal,
    });
  } catch (err) {
    hide(loadingIndicator);
    if (err.name === "AbortError") return; // user interrupted before we even got a response
    showError("Network error talking to the server. Is the backend running?");
    return;
  }

  hide(loadingIndicator);

  // --- Client-side staleness check #1: did a newer question start while we waited? ---
  if (myGenerationId !== currentGenerationId) {
    return; // silently drop the stale response
  }

  let data;
  try {
    data = await response.json();
  } catch {
    showError("Received an unreadable response from the server.");
    return;
  }

  if (!response.ok) {
    if (response.status === 409) {
      // The server itself decided this request was superseded. That's
      // expected during a fast interruption - not an error to show the user.
      return;
    }
    showError(data.detail || "Something went wrong generating the answer.");
    return;
  }

  // --- Client-side staleness check #2: did a newer question start while
  //     the JSON body was being parsed? (rare, but cheap to check) ---
  if (myGenerationId !== currentGenerationId) {
    return;
  }

  addBubble(data.answer_text, "ai");
  playAnswer(data.audio_base64, myGenerationId);
}

function playAnswer(audioBase64, generationId) {
  // One more staleness check right before we touch the audio element.
  if (generationId !== currentGenerationId) return;

  const byteChars = atob(audioBase64);
  const byteNumbers = new Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    byteNumbers[i] = byteChars.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new Blob([byteArray], { type: "audio/mpeg" });

  audioPlayer.src = URL.createObjectURL(blob);
  show(speakingIndicator);
  show(interruptBtn);

  audioPlayer.play().catch(() => {
    showError("Could not play the audio response.");
    hide(speakingIndicator);
    hide(interruptBtn);
  });

  audioPlayer.onended = () => {
    hide(speakingIndicator);
    hide(interruptBtn);
  };
}

// ---------------------------------------------------------------------
// THE INTERRUPT BUTTON - the main feature of this project
// ---------------------------------------------------------------------
function interrupt() {
  // 1. Stop whatever is currently playing, immediately.
  audioPlayer.pause();
  audioPlayer.currentTime = 0;
  hide(speakingIndicator);

  // 2. Cancel any in-flight network request (LLM or Rime call still running).
  if (activeAbortController) {
    activeAbortController.abort();
    activeAbortController = null;
  }

  // 3. Bump the generation id. This invalidates:
  //      - any response that is still in flight and arrives late
  //      - any audio that was about to be played
  currentGenerationId += 1;

  // Mark the last AI bubble as stale/interrupted so the transcript is honest
  // about what happened.
  const lastAiBubble = conversation.querySelector(".bubble.ai:last-of-type");
  if (lastAiBubble && !lastAiBubble.classList.contains("stale")) {
    lastAiBubble.classList.add("stale");
  }

  setInterruptionCount(interruptionCount + 1);
  hide(interruptBtn);

  // 4. Immediately start listening for the new question, so the user can
  //    naturally redirect the AI without clicking the mic button again.
  startListening();
}

// ---------------------------------------------------------------------
// Wire up buttons
// ---------------------------------------------------------------------
micBtn.addEventListener("click", startListening);
interruptBtn.addEventListener("click", interrupt);
