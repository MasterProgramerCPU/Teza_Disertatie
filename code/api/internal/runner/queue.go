package runner

import (
	"github.com/google/uuid"
)

type JobMessage struct {
	SimulationID uuid.UUID `json:"simulation_id"`
	DatasetID    uuid.UUID `json:"dataset_id"`
	Beta         float64   `json:"beta"`
	Gamma        float64   `json:"gamma"`
	PopulationN  int64     `json:"population_n"`
	TMax         int       `json:"t_max"`
	S0           float64   `json:"s0"`
	I0           float64   `json:"i0"`
	R0           float64   `json:"r0"`
	DBDSN        string    `json:"db_dsn"`
}

func QueueName(language string) string {
	return "sir:jobs:" + language
}
