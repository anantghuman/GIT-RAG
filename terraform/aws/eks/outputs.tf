output "cluster_name" {
  value = module.eks.cluster_name
}

output "api_ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "worker_ecr_repository_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "postgres_endpoint" {
  value = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "kafka_bootstrap_brokers" {
  value = aws_msk_cluster.kafka.bootstrap_brokers
}

output "snapshot_bucket" {
  value = aws_s3_bucket.snapshots.id
}

output "runtime_secret_arn" {
  value = aws_secretsmanager_secret.runtime.arn
}
