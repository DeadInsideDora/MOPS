// Ensure indexes for iot.messages
db = db.getSiblingDB('iot');

db.messages.createIndex({ device_id: 1 });
db.messages.createIndex({ ts: -1 });
db.messages.createIndex({ device_id: 1, ts: -1 });
