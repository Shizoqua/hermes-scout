# Releasing Larkspur

We release from `main` every weekday afternoon.

## Blue-green releases

Two identical stacks run side by side, called blue and green. Only one receives traffic.

1. Build the image and push it with the commit hash as its tag.
2. Start the idle colour with the new image and run the smoke checks against it.
3. Flip the load balancer to the idle colour. Users never see an outage.
4. Keep the old colour running for an hour so a flip back is instant.

## Rolling back

Flip the load balancer back to the previous colour. Never edit a running container by hand.
