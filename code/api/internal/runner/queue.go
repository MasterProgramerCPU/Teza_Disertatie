package runner

import (
	"github.com/google/uuid"
)

type JobMessage struct {
	SimulationID uuid.UUID          `json:"simulation_id"`
	DatasetID    uuid.UUID          `json:"dataset_id"`
	ModelType    string             `json:"model_type"`
	Parameters   map[string]float64 `json:"parameters"`
	PopulationN  int64              `json:"population_n"`
	TMax         int                `json:"t_max"`
	Initial      map[string]float64 `json:"initial,omitempty"`
	DBDSN        string             `json:"db_dsn"`
	// ScriptContent este populat doar pentru simulari de tip 'script'
	// (rulate de executor-ul partajat runner-script).
	ScriptContent string `json:"script_content,omitempty"`
}

func QueueName(language string) string {
	return "epimodel:jobs:" + language
}
