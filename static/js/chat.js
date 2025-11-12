class ChatApp {
    constructor() {
        this.username = '';
        this.lastMessageId = 0;
        this.refreshInterval = null;
        this.messageToDelete = null;
        this.editingMessageId = null;
        this.attachedFiles = [];
        this.initializeEventListeners();
    }

    initialize(username, lastMessageId) {
        this.username = username;
        this.lastMessageId = lastMessageId;
        
        this.loadMessages();
        this.updateOnlineUsers();
        
        // Авто-обновление каждые 2 секунды
        this.refreshInterval = setInterval(() => {
            this.loadMessages();
            this.updateOnlineUsers();
        }, 2000);
        
        // Прокручиваем вниз при загрузке
        setTimeout(() => this.scrollToBottom(), 500);
    }

    initializeEventListeners() {
        // Авто-высота textarea
        document.getElementById('messageInput').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        });

        // Обработчик клавиш
        document.getElementById('messageInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Обработчик файлов
        document.getElementById('fileInput').addEventListener('change', (e) => {
            const files = Array.from(e.target.files);
            if (files.length > 0) {
                this.attachedFiles = files;
                this.showFilePreviews(files);
            }
        });

        // Закрытие модальных окон
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                e.target.classList.remove('active');
            }
        });
    }

    // Автопрокрутка вниз
    scrollToBottom() {
        const messagesContainer = document.getElementById('messages');
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Модальные окна
    showClearChatModal() {
        document.getElementById('clearChatModal').classList.add('active');
    }

    hideClearChatModal() {
        document.getElementById('clearChatModal').classList.remove('active');
    }

    showDeleteMessageModal(messageId) {
        this.messageToDelete = messageId;
        document.getElementById('deleteMessageModal').classList.add('active');
    }

    hideDeleteMessageModal() {
        this.messageToDelete = null;
        document.getElementById('deleteMessageModal').classList.remove('active');
    }

    openMediaModal(url, type) {
        const modal = document.getElementById('mediaModal');
        const image = document.getElementById('modalImage');
        const video = document.getElementById('modalVideo');
        
        if (type === 'image') {
            image.src = url;
            image.style.display = 'block';
            video.style.display = 'none';
        } else if (type === 'video') {
            video.src = url;
            video.style.display = 'block';
            image.style.display = 'none';
        }
        
        modal.classList.add('active');
    }

    closeMediaModal() {
        document.getElementById('mediaModal').classList.remove('active');
        const video = document.getElementById('modalVideo');
        video.pause();
        video.currentTime = 0;
    }

    // Управление файлами
    showFilePreviews(files) {
        const previewsContainer = document.getElementById('filePreviews');
        previewsContainer.innerHTML = '';

        files.forEach((file, index) => {
            const preview = document.createElement('div');
            preview.className = 'file-attachment';
            preview.style.marginBottom = '0.5rem';

            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    preview.innerHTML = `
                        <div class="file-icon">🖼️</div>
                        <div class="file-info">
                            <div class="file-name">${file.name}</div>
                            <div class="file-size">${this.formatFileSize(file.size)}</div>
                        </div>
                        <button class="action-btn delete" onclick="chat.removeFile(${index})">×</button>
                    `;
                }.bind(this);
                reader.readAsDataURL(file);
            } else if (file.type.startsWith('video/')) {
                preview.innerHTML = `
                    <div class="file-icon">🎥</div>
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-size">${this.formatFileSize(file.size)}</div>
                    </div>
                    <button class="action-btn delete" onclick="chat.removeFile(${index})">×</button>
                `;
            } else {
                preview.innerHTML = `
                    <div class="file-icon">📎</div>
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-size">${this.formatFileSize(file.size)}</div>
                    </div>
                    <button class="action-btn delete" onclick="chat.removeFile(${index})">×</button>
                `;
            }

            previewsContainer.appendChild(preview);
        });
    }

    removeFile(index) {
        this.attachedFiles.splice(index, 1);
        document.getElementById('fileInput').value = '';
        this.showFilePreviews(this.attachedFiles);
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Редактирование сообщений
    startEditMessage(messageId, currentContent) {
        if (this.editingMessageId) {
            this.cancelEditMessage(this.editingMessageId);
        }
        
        this.editingMessageId = messageId;
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        const contentElement = messageElement.querySelector('.message-content');
        
        // Сохраняем оригинальный контент
        messageElement.setAttribute('data-original-content', currentContent);
        
        // Заменяем контент на поле редактирования
        contentElement.innerHTML = `
            <textarea class="edit-input" rows="3">${currentContent}</textarea>
            <div class="edit-actions">
                <button class="edit-btn cancel" onclick="chat.cancelEditMessage(${messageId})">Cancel</button>
                <button class="edit-btn save" onclick="chat.saveEditedMessage(${messageId})">Save</button>
            </div>
        `;
        
        // Фокус на поле редактирования
        const editInput = contentElement.querySelector('.edit-input');
        editInput.focus();
        editInput.setSelectionRange(editInput.value.length, editInput.value.length);
    }

    cancelEditMessage(messageId) {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        const contentElement = messageElement.querySelector('.message-content');
        const originalContent = messageElement.getAttribute('data-original-content');
        
        contentElement.innerHTML = originalContent;
        this.editingMessageId = null;
    }

    async saveEditedMessage(messageId) {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        const editInput = messageElement.querySelector('.edit-input');
        const newContent = editInput.value.trim();
        
        if (!newContent) {
            this.cancelEditMessage(messageId);
            return;
        }
        
        try {
            const response = await fetch(`/api/messages/${messageId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content: newContent })
            });
            
            if (response.ok) {
                const contentElement = messageElement.querySelector('.message-content');
                contentElement.innerHTML = newContent;
                this.editingMessageId = null;
                
                // Обновляем сообщение у всех через WebSocket
                setTimeout(() => this.loadMessages(), 100);
            } else {
                alert('Error updating message');
                this.cancelEditMessage(messageId);
            }
        } catch (error) {
            console.error('Error updating message:', error);
            this.cancelEditMessage(messageId);
        }
    }

    // Управление сообщениями
    deleteMessage(messageId) {
        this.showDeleteMessageModal(messageId);
    }

    async confirmDeleteMessage() {
        if (!this.messageToDelete) return;
        
        try {
            const response = await fetch(`/api/messages/${this.messageToDelete}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                const messageElement = document.querySelector(`[data-message-id="${this.messageToDelete}"]`);
                if (messageElement) {
                    messageElement.style.opacity = '0';
                    messageElement.style.transform = 'translateY(-10px)';
                    setTimeout(() => messageElement.remove(), 300);
                }
                this.hideDeleteMessageModal();
            }
        } catch (error) {
            console.error('Error deleting message:', error);
        }
    }

    async clearAllMessages() {
        try {
            const response = await fetch('/api/messages', {
                method: 'DELETE'
            });
            
            if (response.ok) {
                // ОСТАНОВИТЬ авто-обновление
                clearInterval(this.refreshInterval);
                
                const messagesContainer = document.getElementById('messages');
                messagesContainer.innerHTML = '';
                this.lastMessageId = 0;
                
                // ЗАПУСТИТЬ снова через 10 секунд
                setTimeout(() => {
                    this.refreshInterval = setInterval(() => {
                        this.loadMessages();
                        this.updateOnlineUsers();
                    }, 2000);
                }, 10000);
                
                this.hideClearChatModal();
            }
        } catch (error) {
            console.error('Error clearing chat:', error);
        }
    }

    // Отправка сообщений с файлами
    async sendMessage() {
        const input = document.getElementById('messageInput');
        const content = input.value.trim();
        const sendButton = document.getElementById('sendButton');
        
        // Блокируем кнопку отправки
        sendButton.disabled = true;
        sendButton.textContent = 'Sending...';

        try {
            if (this.attachedFiles.length > 0) {
                await this.sendMessageWithFiles(content);
            } else if (content) {
                await this.sendTextMessage(content);
            }
            
            // Очищаем поле ввода и файлы
            input.value = '';
            this.attachedFiles = [];
            document.getElementById('filePreviews').innerHTML = '';
            document.getElementById('fileInput').value = '';
            
            // Прокручиваем вниз
            setTimeout(() => this.scrollToBottom(), 100);
            
            // Загружаем новые сообщения
            setTimeout(() => this.loadMessages(), 300);
            
        } catch (error) {
            console.error('Error sending message:', error);
            alert('Error sending message: ' + error.message);
        } finally {
            // Разблокируем кнопку
            sendButton.disabled = false;
            sendButton.textContent = 'Send';
        }
    }

    async sendTextMessage(content) {
        const response = await fetch('/api/messages', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ content: content })
        });
        
        if (!response.ok) {
            throw new Error('Failed to send message');
        }
    }

    async sendMessageWithFiles(content) {
        const formData = new FormData();
        
        // Добавляем текст сообщения
        if (content) {
            formData.append('content', content);
        }
        
        // Добавляем файлы
        this.attachedFiles.forEach(file => {
            formData.append('files', file);
        });

        // Показываем прогресс загрузки
        const progressContainer = document.getElementById('uploadProgress');
        const progressFill = progressContainer.querySelector('.progress-fill');
        const progressText = progressContainer.querySelector('.progress-text');
        
        progressContainer.classList.remove('hidden');

        try {
            const response = await this.fetchWithProgress('/api/upload', {
                method: 'POST',
                body: formData,
                onUploadProgress: (progressEvent) => {
                    if (progressEvent.lengthComputable) {
                        const percentComplete = (progressEvent.loaded / progressEvent.total) * 100;
                        progressFill.style.width = percentComplete + '%';
                        progressText.textContent = Math.round(percentComplete) + '%';
                    }
                }
            });

            if (!response.ok) {
                throw new Error('Failed to upload files');
            }
        } finally {
            // Скрываем прогресс
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                progressFill.style.width = '0%';
                progressText.textContent = '0%';
            }, 1000);
        }
    }

    // XMLHttpRequest с прогрессом
    async fetchWithProgress(url, options = {}) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            xhr.upload.onprogress = function(e) {
                if (options.onUploadProgress && e.lengthComputable) {
                    options.onUploadProgress(e);
                }
            };
            
            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(new Response(xhr.responseText, {
                        status: xhr.status,
                        statusText: xhr.statusText
                    }));
                } else {
                    reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                }
            };
            
            xhr.onerror = function() {
                reject(new Error('Network error'));
            };
            
            xhr.open(options.method || 'GET', url);
            xhr.send(options.body);
        });
    }

    // Функции чата
    async loadMessages() {
        try {
            const response = await fetch('/api/messages');
            const messages = await response.json();
            
            const newMessages = messages.filter(msg => msg.id > this.lastMessageId);
            if (newMessages.length > 0) {
                newMessages.forEach(message => {
                    this.addMessageToDOM(message);
                    this.lastMessageId = Math.max(this.lastMessageId, message.id);
                });
                
                // Авто-скролл к новым сообщениям
                this.scrollToBottom();
            }
        } catch (error) {
            console.error('Error loading messages:', error);
        }
    }

    addMessageToDOM(message) {
        const messages = document.getElementById('messages');
        const existingMessage = document.querySelector(`[data-message-id="${message.id}"]`);
        
        // Если сообщение уже есть (при редактировании), обновляем его
        if (existingMessage) {
            const contentElement = existingMessage.querySelector('.message-content');
            if (contentElement && !this.editingMessageId) {
                contentElement.innerHTML = this.formatMessageContent(message);
            }
            return;
        }
        
        // Создаем новое сообщение
        const msgDiv = document.createElement('div');
        const isOwnMessage = message.username === this.username;
        
        msgDiv.className = `message ${isOwnMessage ? 'own-message' : 'other-message'}`;
        msgDiv.setAttribute('data-message-id', message.id);
        
        const time = new Date(message.created_at).toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: false
        });
        
        msgDiv.innerHTML = `
            <div class="message-header">
                <span class="message-sender">${message.username}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-content">
                ${this.formatMessageContent(message)}
            </div>
            ${isOwnMessage ? `
            <div class="message-actions">
                <button class="action-btn edit" onclick="chat.startEditMessage(${message.id}, '${(message.content || '').replace(/'/g, "\\'").replace(/"/g, '\\"')}')" title="Edit message">
                    ✏️
                </button>
                <button class="action-btn delete" onclick="chat.deleteMessage(${message.id})" title="Delete message">
                    ×
                </button>
            </div>
            ` : ''}
        `;
        
        messages.appendChild(msgDiv);
        
        // Прокручиваем вниз если это новое сообщение
        if (isOwnMessage) {
            setTimeout(() => this.scrollToBottom(), 100);
        }
    }

    formatMessageContent(message) {
        let content = message.content || '';
        
        if (message.file_url) {
            if (message.file_type === 'image') {
                content += `
                    <div class="media-content">
                        <img src="${message.file_url}" alt="Uploaded image" class="media-image" onclick="chat.openMediaModal('${message.file_url}', 'image')">
                    </div>
                `;
            } else if (message.file_type === 'video') {
                content += `
                    <div class="media-content">
                        <video controls class="media-video">
                            <source src="${message.file_url}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                `;
            } else {
                content += `
                    <div class="file-attachment">
                        <div class="file-icon">📎</div>
                        <div class="file-info">
                            <div class="file-name">${message.file_name || 'File'}</div>
                            <div class="file-size">${message.file_size || ''}</div>
                        </div>
                        <a href="${message.file_url}" class="file-download" download="${message.file_name || 'file'}">Download</a>
                    </div>
                `;
            }
        }
        
        return content;
    }

    async updateOnlineUsers() {
        try {
            const response = await fetch('/online-users');
            const data = await response.json();
            
            const onlineList = document.getElementById('onlineUsersList');
            const otherUsers = data.online_users.filter(user => user !== this.username);
            
            onlineList.innerHTML = `
                <div class="user-item">
                    <div class="user-avatar">${this.username[0].toUpperCase()}</div>
                    <div class="user-info">
                        <div class="user-name">${this.username}</div>
                        <div class="user-status">Online</div>
                    </div>
                    <div class="status-indicator self"></div>
                </div>
                ${otherUsers.map(user => `
                    <div class="user-item">
                        <div class="user-avatar">${user[0].toUpperCase()}</div>
                        <div class="user-info">
                            <div class="user-name">${user}</div>
                            <div class="user-status">Online</div>
                        </div>
                        <div class="status-indicator"></div>
                    </div>
                `).join('')}
            `;
        } catch (error) {
            // Silent fail
        }
    }

    logout() {
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        window.location.href = '/';
    }
}

// Глобальный объект чата
const chat = new ChatApp();

// Функция инициализации для HTML
function initializeChat(username, lastMessageId) {
    chat.initialize(username, lastMessageId);
}

// Глобальные функции для вызовов из HTML
function showClearChatModal() { chat.showClearChatModal(); }
function hideClearChatModal() { chat.hideClearChatModal(); }
function deleteMessage(messageId) { chat.deleteMessage(messageId); }
function hideDeleteMessageModal() { chat.hideDeleteMessageModal(); }
function confirmDeleteMessage() { chat.confirmDeleteMessage(); }
function clearAllMessages() { chat.clearAllMessages(); }
function sendMessage() { chat.sendMessage(); }
function logout() { chat.logout(); }
function openMediaModal(url, type) { chat.openMediaModal(url, type); }
function closeMediaModal() { chat.closeMediaModal(); }
function startEditMessage(messageId, content) { chat.startEditMessage(messageId, content); }
function cancelEditMessage(messageId) { chat.cancelEditMessage(messageId); }
function saveEditedMessage(messageId) { chat.saveEditedMessage(messageId); }