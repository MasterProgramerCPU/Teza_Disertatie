// Package k8s contine un manager subtire peste client-go pentru provisioning-ul
// runner-elor plug-in. Singura responsabilitate este sa creeze si sa stearga
// Deployment-uri pentru runner-e: in modul script imaginea este cea generica
// runner-custom (cfg.Image), iar in modul image se foloseste imaginea data
// explicit de super-admin. Toata logica de dispecerizare a job-urilor ramane
// in API + Redis, ca pentru runner-ele built-in.
package k8s

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

// Config descrie parametrii necesari pentru a contacta clusterul si pentru a
// configura pod-urile create. Toti vin din variabile de mediu in main().
type Config struct {
	Enabled    bool   // setare globala: dacă nu, manager-ul devine no-op (dev local)
	Namespace  string // namespace-ul in care se creeaza Deployment-urile
	Image      string // imaginea runner-custom (ex. ghcr.io/.../emedicine-runner-custom:latest)
	ConfigMap  string // ConfigMap din care se citeste REDIS_URL
	SecretName string // Secret din care se citeste DATABASE_URL
	PullSecret string // imagePullSecret pentru registry-ul privat
}

type Manager struct {
	cfg    Config
	client *kubernetes.Clientset
}

func New(cfg Config) (*Manager, error) {
	if !cfg.Enabled {
		return &Manager{cfg: cfg}, nil // no-op manager
	}
	restCfg, err := rest.InClusterConfig()
	if err != nil {
		return nil, fmt.Errorf("k8s in-cluster config: %w", err)
	}
	cs, err := kubernetes.NewForConfig(restCfg)
	if err != nil {
		return nil, fmt.Errorf("k8s clientset: %w", err)
	}
	return &Manager{cfg: cfg, client: cs}, nil
}

func (m *Manager) Enabled() bool { return m.cfg.Enabled }

// DeploymentName produce un nume DNS-safe pe baza id-ului runner-ului. Folosim
// primele 8 caractere ca sa ramana sub limita Kubernetes de 63 caractere
// pentru label-uri/nume.
func DeploymentName(runnerID uuid.UUID) string {
	return "runner-custom-" + runnerID.String()[:8]
}

// CreateRunnerDeployment provisioneaza un Deployment cu 1 replica pentru
// runner-ul cu id-ul si numele dat. Daca imageOverride e gol, foloseste
// imaginea generica runner-custom (cfg.Image) si wrapper-ul ei incarca scriptul
// pe baza RUNNER_ID; daca imageOverride e dat, foloseste exact acea imagine
// (presupusa “runner protocol”-compliant: consuma joburi din RUNNER_QUEUE,
// scrie rezultate in DB). Returneaza numele Deployment-ului creat sau sir gol
// daca manager-ul nu e activ.
func (m *Manager) CreateRunnerDeployment(ctx context.Context, runnerID uuid.UUID,
	runnerName, queueName, imageOverride string) (string, error) {
	if !m.cfg.Enabled {
		return "", nil
	}
	name := DeploymentName(runnerID)
	image := m.cfg.Image
	if imageOverride != "" {
		image = imageOverride
	}
	replicas := int32(1)
	dep := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: m.cfg.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":     "runner-custom",
				"app.kubernetes.io/instance": name,
				"app.kubernetes.io/part-of":  "epimodel",
				"epimodel.io/runner-id":      runnerID.String(),
				"epimodel.io/runner-name":    runnerName,
			},
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: &replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app.kubernetes.io/instance": name,
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app.kubernetes.io/name":     "runner-custom",
						"app.kubernetes.io/instance": name,
						"app.kubernetes.io/part-of":  "epimodel",
					},
				},
				Spec: corev1.PodSpec{
					ImagePullSecrets: []corev1.LocalObjectReference{
						{Name: m.cfg.PullSecret},
					},
					Containers: []corev1.Container{
						{
							Name:            "runner",
							Image:           image,
							ImagePullPolicy: corev1.PullAlways,
							Env: []corev1.EnvVar{
								{Name: "RUNNER_ID", Value: runnerID.String()},
								{Name: "RUNNER_QUEUE", Value: queueName},
								{
									Name: "DATABASE_URL",
									ValueFrom: &corev1.EnvVarSource{
										SecretKeyRef: &corev1.SecretKeySelector{
											LocalObjectReference: corev1.LocalObjectReference{Name: m.cfg.SecretName},
											Key:                  "DATABASE_URL",
										},
									},
								},
								{
									Name: "REDIS_URL",
									ValueFrom: &corev1.EnvVarSource{
										ConfigMapKeyRef: &corev1.ConfigMapKeySelector{
											LocalObjectReference: corev1.LocalObjectReference{Name: m.cfg.ConfigMap},
											Key:                  "REDIS_URL",
										},
									},
								},
							},
							Resources: corev1.ResourceRequirements{
								Limits: corev1.ResourceList{
									corev1.ResourceMemory: resource.MustParse("512Mi"),
									corev1.ResourceCPU:    resource.MustParse("500m"),
								},
								Requests: corev1.ResourceList{
									corev1.ResourceMemory: resource.MustParse("128Mi"),
									corev1.ResourceCPU:    resource.MustParse("100m"),
								},
							},
						},
					},
				},
			},
		},
	}
	_, err := m.client.AppsV1().Deployments(m.cfg.Namespace).Create(ctx, dep, metav1.CreateOptions{})
	if err != nil && !apierrors.IsAlreadyExists(err) {
		return "", fmt.Errorf("create deployment %s: %w", name, err)
	}
	return name, nil
}

// DeleteRunnerDeployment sterge Deployment-ul (si implicit pod-ul) asociat unui
// runner. Idempotent: ignora not-found.
func (m *Manager) DeleteRunnerDeployment(ctx context.Context, deploymentName string) error {
	if !m.cfg.Enabled || deploymentName == "" {
		return nil
	}
	err := m.client.AppsV1().Deployments(m.cfg.Namespace).Delete(ctx, deploymentName, metav1.DeleteOptions{})
	if err != nil && !apierrors.IsNotFound(err) {
		return fmt.Errorf("delete deployment %s: %w", deploymentName, err)
	}
	return nil
}
