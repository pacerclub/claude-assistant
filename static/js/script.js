marked.setOptions({
  headerIds: false,
  mangle: false,
  breaks: true,
  gfm: true,
});

function renderMessage(content, isRawHTML = false) {
  if (isRawHTML) {
    return content
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Use marked to parse the markdown
  let processedContent = marked.parse(content);

  // Sanitize the content
  processedContent = DOMPurify.sanitize(processedContent, {
    ALLOW_DATA_ATTR: false,
    ADD_ATTR: ["target", "class"],
    FORBID_TAGS: ["style", "input", "form", "script", "iframe"],
    FORBID_ATTR: ["style", "onerror", "onload"],
  });

  // Create a temporary div to hold the content
  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = processedContent;

  // Find all code blocks and apply custom syntax highlighting
  tempDiv.querySelectorAll("pre code").forEach((block) => {
    customHighlight(block);
  });

  return tempDiv.innerHTML;
}

function customHighlight(block) {
  let language = block.getAttribute("class");
  if (language) {
    language = language.replace("language-", "");
  } else {
    language = "plaintext";
  }

  // Escape HTML entities in the code
  let code = block.textContent
    .replace(/&/g, "&")
    .replace(/</g, "<")
    .replace(/>/g, ">")
    .replace(/"/g, '"')
    .replace(/'/g, "'");

  try {
    // Disable the console temporarily to suppress warnings
    const originalConsoleWarn = console.warn;
    console.warn = function () {};

    code = hljs.highlight(code, {
      language: language,
      ignoreIllegals: true,
    }).value;

    // Restore the console
    console.warn = originalConsoleWarn;

    // Create code block header
    const header = document.createElement("div");
    header.className = "code-block-header";
    header.innerHTML = `
      <span class="language">${language}</span>
      <button class="copy-button" onclick="copyCode(this)">
        <i class="fas fa-copy"></i>
      </button>
    `;

    // Wrap the code block in a container
    const container = document.createElement("div");
    container.appendChild(header);

    const pre = document.createElement("pre");
    pre.innerHTML = `<code class="hljs ${language}">${code}</code>`;
    container.appendChild(pre);

    // Replace the original code block with the new container
    block.parentNode.replaceWith(container);
  } catch (e) {
    console.warn(`Failed to highlight code block: ${e.message}`);
    // If highlighting fails, just use the escaped code
    block.textContent = code;
  }
}

function hideTypingIndicator() {
  const typingIndicator = document.querySelector(".typing-indicator");
  if (typingIndicator) {
    typingIndicator.remove();
  }
}

async function sendMessage() {
  if (!currentConversationId) {
    alert("Please select or create a conversation first.");
    return;
  }

  const userInput = document.getElementById("user-input");
  const messages = document.getElementById("messages");

  const userMessage = userInput.value;
  if (!userMessage.trim()) return;

  removeEmptyState();

  const isRawHTML = userMessage.startsWith("<") && userMessage.endsWith(">");

  const userMessageDiv = document.createElement("div");
  userMessageDiv.className = "message user";
  userMessageDiv.innerHTML = `<div class="markdown-content">${renderMessage(userMessage, isRawHTML)}</div>`;
  messages.appendChild(userMessageDiv);

  const messageToBeSent = userInput.value;
  userInput.value = "";

  scrollToBottom();
  showTypingIndicator();

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: messageToBeSent,
        conversation_id: currentConversationId,
      }),
    });

    if (response.ok) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiMessageDiv = document.createElement("div");
      aiMessageDiv.className = "message assistant";
      let aiMessageContentDiv = document.createElement("div");
      aiMessageContentDiv.className = "markdown-content";
      aiMessageDiv.appendChild(aiMessageContentDiv);
      messages.appendChild(aiMessageDiv);

      hideTypingIndicator();

      let fullText = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        fullText += decoder.decode(value);
        aiMessageContentDiv.innerHTML = renderMessage(fullText);
        function customHighlightAll() {
          document.querySelectorAll("pre code").forEach(customHighlight);
        }
        scrollToBottom();
      }
    } else {
      throw new Error("Failed to send message");
    }
  } catch (error) {
    console.error("Error:", error);
    alert("An error occurred while sending the message. Please try again.");
  } finally {
    hideTypingIndicator();
    scrollToBottom();
  }
}

function scrollToBottom() {
  const messages = document.getElementById("messages");
  messages.scrollTop = messages.scrollHeight;
}

function handleKeyDown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

let currentConversationId = null;

function formatDate(date) {
  const options = {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  };
  return new Date(date).toLocaleString("en-US", options);
}

function newConversation() {
  const now = new Date();
  const title = formatDate(now);
  fetch("/new_conversation", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: `title=${encodeURIComponent(title)}`,
  })
    .then((response) => response.json())
    .then((data) => {
      const conversationList = document.getElementById("conversation-list");
      const li = document.createElement("li");
      li.className = "conversation-item";
      li.setAttribute("data-id", data.id);
      li.innerHTML = `
        <span class="title" onclick="loadConversation(${data.id})">
          ${data.title}
        </span>
        <div class="conversation-actions">
          <button class="edit-btn" onclick="editConversationTitle(${data.id})">
            <i class="fas fa-edit"></i>
          </button>
          <button class="delete-btn" onclick="deleteConversation(${data.id})">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      `;
      conversationList.prepend(li);
      loadConversation(data.id);
    });
}

function loadConversation(conversationId) {
  currentConversationId = conversationId;
  const messages = document.getElementById("messages");
  messages.innerHTML = "";

  fetch(`/get_conversation/${conversationId}`)
    .then((response) => response.json())
    .then((data) => {
      if (data.error) {
        alert(data.error);
        return;
      }

      // Update the conversation title
      const conversationTitle = document.getElementById("conversation-title");
      const activeItem = document.querySelector(
        `.conversation-item[data-id='${conversationId}']`,
      );
      if (activeItem) {
        conversationTitle.textContent = activeItem.querySelector(".title").textContent.trim();
      }

      if (data.messages.length === 0) {
        messages.innerHTML = `
          <div class="empty-state">
            <i class="fas fa-comments"></i>
            <p>This conversation is empty. Start by sending a message!</p>
          </div>
        `;
      } else {
        removeEmptyState(); // Remove empty state if there are messages
        data.messages.forEach((msg) => {
          const messageDiv = document.createElement("div");
          messageDiv.className = `message ${msg.role}`;
          messageDiv.innerHTML = `<div class="markdown-content">${renderMessage(msg.content)}</div>`;
          messages.appendChild(messageDiv);
        });
        function customHighlightAll() {
          document.querySelectorAll("pre code").forEach(customHighlight);
        }
      }

      scrollToBottom();
    });

  const conversationItems = document.getElementsByClassName("conversation-item");
  for (let item of conversationItems) {
    item.classList.remove("active");
  }
  const activeItem = document.querySelector(
    `.conversation-item[data-id='${conversationId}']`,
  );
  if (activeItem) {
    activeItem.classList.add("active");
  }
}

function deleteConversation(conversationId) {
  if (confirm("Are you sure you want to delete this conversation?")) {
    fetch(`/delete_conversation/${conversationId}`, {
      method: "DELETE",
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          const conversationItem = document.querySelector(
            `.conversation-item[data-id='${conversationId}']`,
          );
          if (conversationItem) {
            conversationItem.remove();
          }
          if (currentConversationId === conversationId) {
            currentConversationId = null;
            document.getElementById("messages").innerHTML = "";
            document.getElementById("conversation-title").textContent = "Welcome, {{ username }}";
          }
        } else {
          alert("Failed to delete conversation");
        }
      });
  }
}

function editConversationTitle(conversationId) {
  const conversationItem = document.querySelector(
    `.conversation-item[data-id='${conversationId}']`,
  );
  const titleSpan = conversationItem.querySelector(".title");
  const currentTitle = titleSpan.textContent.trim();
  const newTitle = prompt("Enter new conversation title:", currentTitle);

  if (newTitle && newTitle !== currentTitle) {
    fetch(`/update_conversation_title/${conversationId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title: newTitle }),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        if (data.success) {
          titleSpan.textContent = newTitle;
          if (currentConversationId === conversationId) {
            document.getElementById("conversation-title").textContent = newTitle;
          }
        } else {
          throw new Error("Server indicated failure");
        }
      })
      .catch((error) => {
        console.error("Error updating conversation title:", error);
        alert("An error occurred while updating the conversation title. Please try again.");
      });
  }
}

function showTypingIndicator() {
  const typingIndicator = document.createElement("div");
  typingIndicator.className = "typing-indicator";
  typingIndicator.innerHTML = "<span></span><span></span><span></span>";
  document.getElementById("messages").appendChild(typingIndicator);
  scrollToBottom();
}

function removeEmptyState() {
  const emptyState = document.querySelector(".empty-state");
  if (emptyState) {
    emptyState.remove();
  }
}

window.onload = function () {
  function customHighlightAll() {
    document.querySelectorAll("pre code").forEach(customHighlight);
  }
  const conversations = document.getElementsByClassName("conversation-item");
  if (conversations.length > 0) {
    loadConversation(conversations[0].getAttribute("data-id"));
  } else {
    newConversation();
  }
};

function copyCode(button) {
  const pre = button.closest(".code-block-header").nextElementSibling;
  const code = pre.querySelector("code");
  const textArea = document.createElement("textarea");
  textArea.value = code.textContent;
  document.body.appendChild(textArea);
  textArea.select();
  document.execCommand("copy");
  document.body.removeChild(textArea);

  // Change button icon temporarily
  const icon = button.querySelector("i");
  icon.className = "fas fa-check";
  setTimeout(() => {
    icon.className = "fas fa-copy";
  }, 2000);
}

document.addEventListener("DOMContentLoaded", function () {
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.querySelector(".sidebar");
  const sidebarOverlay = document.querySelector(".sidebar-overlay");

  function toggleSidebar() {
    sidebar.classList.toggle("open");
    sidebarOverlay.classList.toggle("active");
  }

  sidebarToggle.addEventListener("click", toggleSidebar);
  sidebarOverlay.addEventListener("click", toggleSidebar);

  // Close sidebar when clicking outside
  document.addEventListener("click", function (event) {
    const isClickInside = sidebar.contains(event.target) || sidebarToggle.contains(event.target);
    if (!isClickInside && sidebar.classList.contains("open")) {
      toggleSidebar();
    }
  });
});