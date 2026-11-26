 MOVA – Intelligent Travel Discovery and Trip Planning Platform


MOVA is designed to simplify travel planning across India by bringing destination discovery, itinerary planning, travel information and community features together in one platform.

Instead of switching between multiple applications and manually organizing travel information, users can explore destinations, create personalized trip plans and manage their travel experiences through a unified interface.


1. Problem Statement

Planning a trip, especially across multiple destinations in India, can involve several disconnected activities.

Travelers often need to:

- Search across different platforms to discover destinations and attractions.
- Compare transportation options and estimate travel time.
- Plan accommodation, food and travel expenses separately.
- Organize multiple destinations into a practical itinerary.
- Adjust plans when travel constraints or preferences change.
- Find useful information about unfamiliar destinations.

These activities can make travel planning time-consuming, confusing and difficult to manage, particularly for people planning trips across multiple Indian states.

There is a need for a centralized platform that makes destination discovery and trip organization more accessible and structured.

2. Proposed Solution

MOVA proposes an integrated travel-planning platform focused on Indian destinations.

The platform combines destination discovery, preference-based trip planning, itinerary organization, geographic information and community features.

Users can explore destinations, select travel preferences, generate trip plans through the planning engine and make adjustments to their itineraries.

MOVA also uses geographic data sources and routing services where available to support destination discovery and travel planning.

The goal is to make trip planning more organized, accessible and adaptable to different types of travelers.

3. Key Features

 Destination Discovery
- Explore destinations across Indian states.
- Browse destination information and images.
- Discover places of interest.
- Access geographic information through supported external data sources.

Intelligent Trip Planning
- Create trips using destination and travel preferences.
- Support multiple destinations.
- Generate structured itineraries.
- Consider travel constraints and preferences.
- Modify and re-optimize existing itineraries.

Travel Information
- Access geographic and place information.
- Integrate road-routing information when available.
- Provide travel-method recommendations.
- Distinguish between live information, estimates and unavailable integrations.

Community
- Dedicated community interface.
- Community-oriented travel interactions.
- Profile and post-related interface features.

User Experience
- Responsive web interface.
- Light and dark appearance modes.
- Destination and place details.
- Trip dashboard and itinerary management.
- Authentication interface using Firebase.

**Note:** Feature availability and persistence depend on the current implementation and configured services. Not all features are connected to production cloud storage.

4. Technology Stack

| Component | Technologies |
|---|---|
| Frontend | HTML5, CSS3, JavaScript |
| Backend | Python, FastAPI |
| Data validation | Pydantic |
| Authentication | Firebase Authentication |
| Geographic data | OpenStreetMap ecosystem |
| Place discovery | Nominatim, Overpass |
| Road routing | OSRM, when available |
| Map interface | Leaflet and OpenStreetMap |
| Destination information | Wikipedia and other supported public sources |
| Version control | Git and GitHub |

The application uses a modular frontend and a Python-based backend planning engine.

5. System Architecture

MOVA follows a frontend-backend architecture.

Frontend
The frontend is built using HTML, CSS and JavaScript.

It manages:
- User interface and navigation.
- Destination discovery.
- User interactions and preferences.
- Trip creation and itinerary display.
- API communication.
- Profile and community interfaces.

Backend
The backend uses FastAPI and Python.

The travel-planning engine contains:
- Recommendation services.
- Travel-time and travel-cost services.
- Constraint handling.
- Itinerary optimization.
- Plan modification and re-optimization.
- Itinerary validation.
- API endpoints for planning operations.

External Data and Services
MOVA integrates supported external services for:
- Geographic place discovery.
- Destination information.
- Road-routing information.
- Map visualization.

 General Workflow

```text
              USER
                |
                v
        MOVA WEB FRONTEND
                |
                v
          API CONNECTION
                |
                v
          FASTAPI BACKEND
                |
                v
        TRAVEL PLANNING ENGINE
                |
        +-------+-------+
        |       |       |
        v       v       v
   Recommendation  Constraints  Optimization
        |       |       |
        +-------+-------+
                |
                v
       STRUCTURED ITINERARY
                |
                v
        FRONTEND DISPLAY
```

External geographic and information services support relevant discovery and routing operations.

6. Project Structure

```text
MOVA/
│
├── index.html
│
├── pages/
│   ├── community.html
│   ├── create-plan.html
│   └── other application pages
│
├── css/
│   └── Frontend stylesheets
│
├── js/
│   ├── api.js
│   ├── auth.js
│   ├── community.js
│   ├── discover.js
│   ├── edit-plan.js
│   ├── firebase-config.js
│   ├── home.js
│   ├── place-details.js
│   ├── plan-dashboard.js
│   ├── plans.js
│   ├── profile.js
│   └── region-details.js
│
├── data/
│   ├── cities.json
│   ├── destinations.json
│   ├── places.json
│   ├── hotels.json
│   └── other data files
│
├── assets/
│   ├── images/
│   └── patterns/
│
├── backend/
│   └── mova_travel_engine/
│       ├── app/
│       ├── data/
│       ├── tests/
│       └── requirements.txt
│
├── start_mova_backend.ps1
├── start_mova_backend.bat
├── start_mova_frontend.bat
├── start_mova_all.bat
│
├── BACKEND_CONNECTION.md
├── FIREBASE_SETUP.md
├── .gitignore
└── README.md
```

Some internal files and directories are omitted from this overview for readability.

7. Installation Requirements

Before running MOVA locally, make sure you have:

- Windows 10 or later (for the provided launch scripts).
- Python installed.
- Git installed.
- Visual Studio Code or another code editor.
- A modern web browser.
- Internet access for external geographic and information services.

8. Installation and Setup

Step 1: Clone the repository

Open PowerShell or a terminal and run:

```bash
git clone https://github.com/soumikamika/MOVA.git
```

Step 2: Open the project

```bash
cd MOVA
```

Open the folder in Visual Studio Code if desired:

```bash
code .
```

Step 3: Configure Firebase

MOVA includes Firebase client-side authentication configuration.

Follow the instructions in:

`FIREBASE_SETUP.md`

Use your own Firebase project configuration where required.

Do not commit private service-account credentials, private keys or other secrets to the public repository.

Step 4: Configure the backend

Navigate to:

`backend/mova_travel_engine/`

Review the environment configuration examples and backend documentation.

Do not put real credentials into the example environment files.

9. How to Run MOVA

Option A: Start the backend

From the MOVA root directory, open PowerShell and execute:

```powershell
.\start_mova_backend.ps1
```

Alternatively, use:

```text
start_mova_backend.bat
```

The backend launcher prepares the local Python environment and installs the required dependencies when needed.

The API is expected to run at:

`http://127.0.0.1:8000`

Health endpoint:

`http://127.0.0.1:8000/api/health`

Option B: Start the frontend

Run:

```text
start_mova_frontend.bat
```

The frontend is expected to be available at:

`http://127.0.0.1:5500`

You can also open `index.html` using the VS Code Live Server extension.

Option C: Start both together

For the combined local setup, execute:

```text
start_mova_all.bat
```

This launcher starts the backend and frontend and opens the application in the browser.

Keep the backend and frontend processes running while using the locally hosted application.

10. Project Workflow

The general MOVA user workflow is:

1. *Explore:* The user opens MOVA and explores available destinations.
2. *Discover:* The user browses destination information and places of interest.
3. *Create a trip:* The user enters trip details and preferences.
4. *Process preferences:* The frontend communicates with the backend planning API.
5. *Generate itinerary:* The planning engine processes available destination data and travel constraints.
6. *View the plan:* The generated itinerary is presented through the frontend.
7. *Modify the trip:* Users can make changes and request supported plan modifications or re-optimization.
8. *Manage the experience:* Users can access the available dashboard, profile and community interfaces.

11. Data Sources and Third-Party Integrations

MOVA uses a combination of bundled project data and external services.

| Source / Service | Purpose |
|---|---|
| OpenStreetMap | Geographic and map data |
| Nominatim | Geographic search and place lookup |
| Overpass API | OpenStreetMap data discovery |
| OSRM | Road-routing information |
| Wikipedia | Destination information |
| Firebase | Client-side authentication |
| Leaflet | Interactive map interface |

External service availability, data coverage and usage policies may affect the application's functionality.

MOVA does not claim ownership of third-party geographic or informational datasets. Their respective licenses and usage requirements apply.

 12. AI Tools and Development Transparency

AI-powered tools were used as development assistants during the planning and implementation of MOVA.

 Tools Used

- *ChatGPT (OpenAI):* Assisted with project planning, frontend and backend development, code generation and modification, debugging and technical problem-solving.
- *Claude (Anthropic):* Assisted with development planning, code modification, backend preparation and technical problem-solving.
- *Google Antigravity:* Used as an AI-assisted development environment during backend preparation and implementation.

 Participant Contributions

The project participant contributed to:
- Defining the MOVA project concept and product direction.
- Identifying the problem and planning the proposed solution.
- Designing the frontend's visual direction and user experience.
- Planning frontend functionality and collaborating on its implementation.
- Making feature and implementation decisions.
- Integrating and testing project components.

AI tools assisted with code generation, modification and development workflows. Their use is disclosed to maintain transparency.

The project is presented as an AI-assisted development effort rather than claiming that all code was independently written without assistance.

 13. Current Limitations

MOVA is an evolving project. The following limitations should be considered:

- Some bundled planner records are development or synthetic data and are not verified live tourism information.
- Geographic discovery depends on external providers and internet connectivity.
- External routing and information services may have rate limits or availability restrictions.
- Some travel times and costs are estimates rather than confirmed real-time values.
- User plans and community data currently have local persistence limitations and are not fully backed by a production cloud database.
- Firebase client-side authentication should not be confused with complete server-side authorization enforcement.
- Production-scale datasets, persistent cloud storage and additional provider integrations remain areas for improvement.

14. Future Scope

Planned improvements include:

- Production-quality travel datasets.
- Persistent cloud database integration.
- Secure server-side authentication and authorization.
- More extensive destination and accommodation information.
- Improved transport and route comparisons.
- More accurate cost estimation.
- Enhanced personalization and recommendations.
- Expanded community features.
- Improved scalability and deployment infrastructure.

## 15. Project Repository

*GitHub:* https://github.com/soumikamika/MOVA

MOVA aims to make travel planning across India more organized by combining destination discovery, intelligent itinerary planning and travel-related community experiences in one platform.
