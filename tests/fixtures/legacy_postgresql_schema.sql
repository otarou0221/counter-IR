CREATE TABLE cameras (
    camera_id VARCHAR(64) PRIMARY KEY,
    camera_code VARCHAR(64) NOT NULL UNIQUE,
    manufacturer VARCHAR(100),
    model_name VARCHAR(100),
    serial_number VARCHAR(100) UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE locations (
    location_id VARCHAR(64) PRIMARY KEY,
    factory_name VARCHAR(100),
    area_name VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE camera_installations (
    camera_installation_id BIGSERIAL PRIMARY KEY,
    camera_id VARCHAR(64) NOT NULL REFERENCES cameras(camera_id),
    location_id VARCHAR(64) NOT NULL REFERENCES locations(location_id),
    ip_address INET NOT NULL,
    port INTEGER NOT NULL,
    installed_at TIMESTAMPTZ NOT NULL,
    removed_at TIMESTAMPTZ,
    mounting_note TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

INSERT INTO cameras (
    camera_id, camera_code, display_name, active, created_at, updated_at
) VALUES
    ('camera_1', 'CAM-001', 'カメラ1', TRUE, now(), now()),
    ('camera_2', 'CAM-002', 'カメラ2', TRUE, now(), now());

INSERT INTO locations (
    location_id, factory_name, area_name, created_at, updated_at
) VALUES
    ('location_camera_1', '工場', 'エリア1', now(), now()),
    ('location_camera_2', '工場', 'エリア2', now(), now());

INSERT INTO camera_installations (
    camera_id, location_id, ip_address, port,
    installed_at, created_at, updated_at
) VALUES
    ('camera_1', 'location_camera_1', '192.168.253.7', 8090, now(), now(), now()),
    ('camera_2', 'location_camera_2', '192.168.253.8', 8090, now(), now(), now());
