from flask import Flask, render_template_string, request

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    selected_choices = request.form.getlist("choices")
    selected_services = request.form.getlist("services")
    selected_providers = request.form.getlist("providers")
    special_access = request.form.get("special_access")  # Yes/No radio
    selected_buildings = request.form.getlist("buildings") if special_access == "Yes" else []

    # Example coordinates (can later map to buildings dynamically)
    latitude = 40.001
    longitude = -83.015

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Vend-nier Form</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>

    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .checkbox-group { margin-bottom: 20px; }
        button, select { padding: 8px 12px; font-size: 16px; }
        .container { display: flex; gap: 20px; align-items: flex-start; }
        .form-container { flex: 1; min-width: 300px; }
        .map-container { flex: 1; min-width: 400px; }
    </style>

    <script>
        function toggleBuildings() {
            const yesRadio = document.getElementById("special_yes");
            const buildingGroup = document.getElementById("building_group");
            buildingGroup.style.display = yesRadio.checked ? "block" : "none";
        }
        window.onload = function() {
            toggleBuildings();

            // Initialize Leaflet map
            const latitude = {{ latitude }};
            const longitude = {{ longitude }};
            const map = L.map('map').setView([latitude, longitude], 16);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);

            L.marker([latitude, longitude]).addTo(map)
                .bindPopup('Your Location')
                .openPopup();
        };
    </script>
</head>
<body>
    <h1><b>Vend-nier:</b></h1>
    <p>Find vending machines "nier" you</p>

    <div class="container">
        <!-- Form on the left -->
        <div class="form-container">
            <form method="POST">
                <!-- Payment Method -->
                <p><b>Payment Method</b></p>
                <div class="checkbox-group">
                    {% for method in ['Visa','Apple Pay','Discover','MasterCard','Google Pay','American Express','Cash','BuckID'] %}
                        <input type="checkbox" name="choices" value="{{ method }}" {% if method in selected_choices %}checked{% endif %}> {{ method }}<br>
                    {% endfor %}
                </div>

                <!-- Service -->
                <p><b>Service</b></p>
                <div class="checkbox-group">
                    {% for service in ['Drinks','Snacks'] %}
                        <input type="checkbox" name="services" value="{{ service }}" {% if service in selected_services %}checked{% endif %}> {{ service }}<br>
                    {% endfor %}
                </div>

                <!-- Provider -->
                <p><b>Provider</b></p>
                <div class="checkbox-group">
                    {% for provider in ['Coca Cola','DASANI','Vitamin Water','Various'] %}
                        <input type="checkbox" name="providers" value="{{ provider }}" {% if provider in selected_providers %}checked{% endif %}> {{ provider }}<br>
                    {% endfor %}
                </div>

                <!-- Special Access -->
                <p><b>Do you have special access to any buildings?</b></p>
                <div class="checkbox-group">
                    <input type="radio" id="special_yes" name="special_access" value="Yes" onclick="toggleBuildings()" {% if special_access=='Yes' %}checked{% endif %}> Yes
                    <input type="radio" id="special_no" name="special_access" value="No" onclick="toggleBuildings()" {% if special_access=='No' %}checked{% endif %}> No
                </div>

                <!-- Conditional Buildings Checkboxes -->
                <div id="building_group" class="checkbox-group" style="display:none;">
                    <p><b>Select Buildings</b></p>
                    {% for building in ['Baker Systems Engineering','Barrett House','Blackburn House','Bradley Hall','Denny Hall','Houck House','Jones Tower','Lincoln Tower','Mack Hall','Mendoza House','Morrill Tower','Morrison Tower','Neil Building','Norton House','Nosker House','Park-Stradley Hall','Paterson Hall','Smith-Steeb Hall','Taylor Tower','Worthington Building'] %}
                        <input type="checkbox" name="buildings" value="{{ building }}" {% if building in selected_buildings %}checked{% endif %}> {{ building }}<br>
                    {% endfor %}
                </div>

                <button type="submit">Submit</button>
            </form>

            <!-- Display selections -->
            {% if selected_choices or selected_services or selected_providers or special_access %}
                <h2>You picked:</h2>

                {% if selected_choices %}
                    <p><b>Payment Methods:</b></p>
                    <ul>{% for item in selected_choices %}<li>{{ item }}</li>{% endfor %}</ul>
                {% endif %}

                {% if selected_services %}
                    <p><b>Services:</b></p>
                    <ul>{% for item in selected_services %}<li>{{ item }}</li>{% endfor %}</ul>
                {% endif %}

                {% if selected_providers %}
                    <p><b>Providers:</b></p>
                    <ul>{% for item in selected_providers %}<li>{{ item }}</li>{% endfor %}</ul>
                {% endif %}

                {% if special_access %}
                    <p><b>Special Access (Yes/No):</b> {{ special_access }}</p>
                    {% if selected_buildings %}
                        <p><b>Buildings:</b></p>
                        <ul>{% for building in selected_buildings %}<li>{{ building }}</li>{% endfor %}</ul>
                    {% endif %}
                {% endif %}
            {% endif %}
        </div>

        <!-- Map on the right -->
        <div class="map-container">
            <div id="map" style="height: 500px; width: 100%;"></div>
        </div>
    </div>
</body>
</html>
""", selected_choices=selected_choices,
         selected_services=selected_services,
         selected_providers=selected_providers,
         special_access=special_access,
         selected_buildings=selected_buildings,
         latitude=latitude,
         longitude=longitude)

if __name__ == "__main__":
    app.run(debug=True)
