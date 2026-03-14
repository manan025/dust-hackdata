package config

const (
	DefaultAddr     = "127.0.0.1"
	DefaultPort     = 8080
	DefaultLogLevel = "info"
	DefaultRebuildImage = false
)

var (
	Addr     = DefaultAddr
	Port     = DefaultPort
	LogLevel = DefaultLogLevel
	RebuildImage = DefaultRebuildImage
)
