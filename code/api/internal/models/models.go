package models

import (
	"time"

	"github.com/google/uuid"
)

type User struct {
	ID           uuid.UUID `json:"id"`
	Email        string    `json:"email"`
	PasswordHash string    `json:"-"`
	IsSuperAdmin bool      `json:"is_super_admin"`
	CreatedAt    time.Time `json:"created_at"`
}

type Dataset struct {
	ID          uuid.UUID `json:"id"`
	UserID      uuid.UUID `json:"user_id"`
	StudyID     uuid.UUID `json:"study_id"`
	Name        string    `json:"name"`
	DiseaseCode string    `json:"disease_code"`
	UploadedAt  time.Time `json:"uploaded_at"`
	RecordCount int       `json:"record_count"`
}

type Study struct {
	ID          uuid.UUID `json:"id"`
	Name        string    `json:"name"`
	DiseaseCode string    `json:"disease_code"`
	Description string    `json:"description,omitempty"`
	CreatedBy   uuid.UUID `json:"created_by"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type StudyRole string

const (
	RoleAdmin       StudyRole = "admin"
	RoleResearcher  StudyRole = "researcher"
	RoleContributor StudyRole = "contributor"
	RoleViewer      StudyRole = "viewer"
)

func ValidStudyRole(s string) bool {
	switch StudyRole(s) {
	case RoleAdmin, RoleResearcher, RoleContributor, RoleViewer:
		return true
	}
	return false
}

type StudyMember struct {
	StudyID  uuid.UUID `json:"study_id"`
	UserID   uuid.UUID `json:"user_id"`
	Email    string    `json:"email,omitempty"`
	Role     StudyRole `json:"role"`
	JoinedAt time.Time `json:"joined_at"`
}

// MembershipForUser e folosit cand listam studiile vizibile unui user
// impreuna cu rolul lui in fiecare.
type MembershipForUser struct {
	Study Study     `json:"study"`
	Role  StudyRole `json:"role"`
}

type EpidemiologicalRecord struct {
	ID           uuid.UUID `json:"id"`
	DatasetID    uuid.UUID `json:"dataset_id"`
	RecordedDate time.Time `json:"recorded_date"`
	RegionCode   string    `json:"region_code"`
	Susceptible  *int64    `json:"susceptible,omitempty"`
	Infected     int64     `json:"infected"`
	Recovered    *int64    `json:"recovered,omitempty"`
	Population   int64     `json:"population"`
}

type SimulationStatus string

type Language string

const (
	LangR      Language = "r"
	LangJulia  Language = "julia"
	LangPython Language = "python"
)

func ValidLanguage(s string) bool {
	switch Language(s) {
	case LangR, LangJulia, LangPython:
		return true
	}
	return false
}

type ModelType string

const (
	ModelSIS      ModelType = "sis"
	ModelSIR      ModelType = "sir"
	ModelSEIR     ModelType = "seir"
	ModelSIRS     ModelType = "sirs"
	ModelSIDARTHE ModelType = "sidarthe"
	ModelLSTM     ModelType = "lstm"
	// ModelScript marcheaza o simulare de tip "rulare ad-hoc de script Python".
	// Pentru aceste simulari coloana script_content trebuie sa fie non-vida si
	// executia o face runner-ul partajat runner-script (vezi Cap. 4 §plug-in-uri).
	ModelScript ModelType = "script"
)

var SupportedModelTypes = []ModelType{
	ModelSIS,
	ModelSIR,
	ModelSEIR,
	ModelSIRS,
	ModelSIDARTHE,
	ModelLSTM,
	ModelScript,
}

func ValidModelType(s string) bool {
	for _, model := range SupportedModelTypes {
		if ModelType(s) == model {
			return true
		}
	}
	return false
}

type SimulationRun struct {
	ID            uuid.UUID          `json:"id"`
	UserID        uuid.UUID          `json:"user_id"`
	StudyID       uuid.UUID          `json:"study_id"`
	DatasetID     uuid.UUID          `json:"dataset_id"`
	ModelType     ModelType          `json:"model_type"`
	Language      Language           `json:"language"`
	Parameters    map[string]float64 `json:"parameters"`
	PopulationN   int64              `json:"population_n"`
	TMax          int                `json:"t_max"`
	ScriptContent string             `json:"script_content,omitempty"`
	Status        SimulationStatus   `json:"status"`
	ErrorMessage  *string            `json:"error_message,omitempty"`
	CreatedAt     time.Time          `json:"created_at"`
	CompletedAt   *time.Time         `json:"completed_at,omitempty"`
}

type SimulationResult struct {
	SimulationID uuid.UUID          `json:"simulation_id"`
	T            int                `json:"t"`
	Compartments map[string]float64 `json:"compartments"`
}

// RunnerStatus reprezinta starea ciclului de viata al unui runner plug-in.
// pending  -> tocmai inregistrat, asteapta build-ul.
// building -> imaginea container se construieste.
// ready    -> deployment-ul ruleaza si runner-ul accepta job-uri.
// failed   -> build sau deploy esuat; status_message contine detalii.
// stopped  -> oprit explicit de super-admin (scale-to-zero, dar inregistrarea ramane).
type RunnerStatus string

const (
	RunnerStatusPending  RunnerStatus = "pending"
	RunnerStatusBuilding RunnerStatus = "building"
	RunnerStatusReady    RunnerStatus = "ready"
	RunnerStatusFailed   RunnerStatus = "failed"
	RunnerStatusStopped  RunnerStatus = "stopped"
)

// Runner descrie un runner de algoritm persistent definit prin imagine
// container, scope-uit la un singur studiu. Imaginea este construita extern
// (in CI sau docker build local) si referita aici; clusterul o trage din
// registry si o ruleaza ca Deployment dedicat, ascultand pe coada Redis
// dedicata. Pentru executia ad-hoc de scripturi Python vezi tabela
// simulation_runs (model_type='script') si executor-ul partajat runner-script.
type Runner struct {
	ID              uuid.UUID      `json:"id"`
	StudyID         uuid.UUID      `json:"study_id"`
	UploadedBy      uuid.UUID      `json:"uploaded_by"`
	Name            string         `json:"name"`
	Description     string         `json:"description"`
	Image           string         `json:"image"`
	ParameterSchema map[string]any `json:"parameter_schema"`
	Status          RunnerStatus   `json:"status"`
	StatusMessage   string         `json:"status_message,omitempty"`
	QueueName       string         `json:"queue_name"`
	DeploymentName  string         `json:"deployment_name,omitempty"`
	CreatedAt       time.Time      `json:"created_at"`
	ReadyAt         *time.Time     `json:"ready_at,omitempty"`
}

type BenchmarkAggregate struct {
	ModelType      ModelType `json:"model_type"`
	Language       Language  `json:"language"`
	RunCount       int       `json:"run_count"`
	MedianWallMs   float64   `json:"median_wall_ms"`
	P95WallMs      float64   `json:"p95_wall_ms"`
	MedianCPUMs    float64   `json:"median_cpu_ms"`
	MedianMemoryMB float64   `json:"median_memory_mb"`
}
