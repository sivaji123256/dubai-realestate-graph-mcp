// Uniqueness constraints on natural keys — lets the loader MERGE idempotently
// and gives Neo4j an index on each lookup key for free.

CREATE CONSTRAINT transaction_id IF NOT EXISTS FOR (t:Transaction) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT area_name IF NOT EXISTS FOR (a:Area) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT building_name IF NOT EXISTS FOR (b:Building) REQUIRE b.name IS UNIQUE;
CREATE CONSTRAINT project_name IF NOT EXISTS FOR (p:Project) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT master_project_name IF NOT EXISTS FOR (m:MasterProject) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT property_type_name IF NOT EXISTS FOR (pt:PropertyType) REQUIRE pt.name IS UNIQUE;
CREATE CONSTRAINT property_subtype_name IF NOT EXISTS FOR (pst:PropertySubType) REQUIRE pst.name IS UNIQUE;
CREATE CONSTRAINT metro_name IF NOT EXISTS FOR (ms:MetroStation) REQUIRE ms.name IS UNIQUE;
CREATE CONSTRAINT mall_name IF NOT EXISTS FOR (ml:Mall) REQUIRE ml.name IS UNIQUE;
CREATE CONSTRAINT landmark_name IF NOT EXISTS FOR (l:Landmark) REQUIRE l.name IS UNIQUE;
CREATE CONSTRAINT user_email IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE;
CREATE CONSTRAINT sync_state_source IF NOT EXISTS FOR (s:SyncState) REQUIRE s.source IS UNIQUE;
