package models

import (
	"time"

	"github.com/google/uuid"
)

type User struct {
	ID           uuid.UUID `json:"id"`
	Email        string    `json:"email"`
	PasswordHash string    `json:"-"`
	CreatedAt    time.Time `json:"created_at"`
}

type Dataset struct {
	ID          uuid.UUID `json:"id"`
	UserID      uuid.UUID `json:"user_id"`
	Name        string    `json:"name"`
	DiseaseCode string    `json:"disease_code"`
	UploadedAt  time.Time `json:"uploaded_at"`
	RecordCount int       `json:"record_count"`
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

const (
	StatusPending   SimulationStatus = "pending"
	StatusRunning   SimulationStatus = "running"
	StatusCompleted SimulationStatus = "completed"
	StatusFailed    SimulationStatus = "failed"
)

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

type SimulationRun struct {
	ID           uuid.UUID        `json:"id"`
	UserID       uuid.UUID        `json:"user_id"`
	DatasetID    uuid.UUID        `json:"dataset_id"`
	Language     Language         `json:"language"`
	Beta         float64          `json:"beta"`
	Gamma        float64          `json:"gamma"`
	PopulationN  int64            `json:"population_n"`
	TMax         int              `json:"t_max"`
	Status       SimulationStatus `json:"status"`
	ErrorMessage *string          `json:"error_message,omitempty"`
	CreatedAt    time.Time        `json:"created_at"`
	CompletedAt  *time.Time       `json:"completed_at,omitempty"`
}

type SimulationResult struct {
	SimulationID uuid.UUID `json:"simulation_id"`
	T            int       `json:"t"`
	S            float64   `json:"s"`
	I            float64   `json:"i"`
	R            float64   `json:"r"`
}

type Benchmark struct {
	ID            uuid.UUID `json:"id"`
	SimulationID  uuid.UUID `json:"simulation_id"`
	WallTimeMs    int64     `json:"wall_time_ms"`
	CPUTimeMs     int64     `json:"cpu_time_ms"`
	PeakMemoryMB  float32   `json:"peak_memory_mb"`
}

type BenchmarkAggregate struct {
	Language        Language `json:"language"`
	RunCount        int      `json:"run_count"`
	MedianWallMs    float64  `json:"median_wall_ms"`
	P95WallMs       float64  `json:"p95_wall_ms"`
	MedianCPUMs     float64  `json:"median_cpu_ms"`
	MedianMemoryMB  float64  `json:"median_memory_mb"`
}
