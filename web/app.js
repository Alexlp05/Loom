document.addEventListener('DOMContentLoaded', () => {
    const timelineContainer = document.getElementById('timeline-container');
    const modal = document.getElementById('story-modal');
    const closeBtn = document.querySelector('.close-btn');
    const modalDate = document.getElementById('modal-date');
    const modalTitle = document.getElementById('modal-title');
    const modalText = document.getElementById('modal-text');

    // Fetch stories from API
    async function loadStories() {
        try {
            const response = await fetch('/api/stories');
            if (!response.ok) throw new Error("Failed to load stories");
            
            const stories = await response.json();
            
            if (stories.length === 0) {
                timelineContainer.innerHTML = '<div class="loading">Aucun souvenir trouvé. Utilisez le téléphone pour en créer !</div>';
                return;
            }

            // Clear loading text
            timelineContainer.innerHTML = '';

            // Generate timeline elements
            stories.forEach((story, index) => {
                const item = document.createElement('div');
                item.className = 'timeline-item';
                item.style.animationDelay = `${index * 0.15}s`;

                const card = document.createElement('div');
                card.className = 'story-card';
                card.innerHTML = `
                    <h3 class="story-title" style="margin-bottom: 0.3rem; font-size: 1.2rem; color: #fff;">${story.title}</h3>
                    <div class="story-date">${story.formatted_date}</div>
                    <div class="story-excerpt">"${story.excerpt}..."</div>
                `;

                // Add click event to open modal
                card.addEventListener('click', () => {
                    openModal(story);
                });

                item.appendChild(card);
                timelineContainer.appendChild(item);
            });

        } catch (error) {
            console.error(error);
            timelineContainer.innerHTML = '<div class="loading" style="color: #ff5e5e;">Erreur lors du chargement des souvenirs. Le serveur API tourne-t-il ?</div>';
        }
    }

    // Modal behavior
    function openModal(story) {
        modalTitle.textContent = story.title;
        modalDate.textContent = story.formatted_date;
        modalText.textContent = story.content;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden'; // Prevent scrolling in background
    }

    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }

    closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // Close on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeModal();
        }
    });

    // Init
    loadStories();
});
