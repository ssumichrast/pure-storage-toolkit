# FlashBlade home directories

An Ansible playbook that creates a home directory on a Pure Storage FlashBlade for each user in a list.

For each user it creates:

1. A file system named `<prefix><username>` (for example `home-alice`).
2. One NFS export named `<home_export_prefix><username>`, using an existing export policy.
3. A QoS policy attached to that file system, so each user is limited on their own.

Nothing else is created. In particular the array's default NFS and SMB exports are suppressed.

It is safe to re-run. Anything that already exists is left alone.

## Requirements

- `ansible-core` 2.16 or later. No Ansible collections are needed.
- A FlashBlade running Purity//FB 4.7.x or later (REST API 2.24).
- An API token for an account that can create file systems, exports and QoS memberships.
- The NFS export policy and QoS policy already exist on the FlashBlade.

## Setup

Copy `vars/configvalues.example.yml` to `vars/configvalues.yml` and set `fb_url` (the array address) and the other site settings below.

Put the API token in `vars/credentials.yml`. The playbook loads it automatically. The file is git-ignored; keep it mode 600.

```
cp vars/credentials.example.yml vars/credentials.yml && chmod 600 vars/credentials.yml
# then edit fb_api_token
```

Edit `vars/configvalues.yml` for your site:

| Setting | Meaning |
| --- | --- |
| `home_fs_prefix` | Prefix for each file system, e.g. `home-`, `home_`, `h_` |
| `home_export_prefix` | Prefix for each export name, e.g. `home-` (`""` for none) |
| `home_realm` | Realm to create the file systems in (`""` for none); users can override it. See "Realms" below |
| `home_export_policy` | Existing NFS export policy to attach to each export |
| `home_qos_policy` | Default QoS policy for every user |
| `home_fs_size_gib` | Default file system size in GiB (thin provisioned) |

## Listing users

Copy `vars/home_users.example.yml` to `vars/home_users.yml` and edit it. Each entry is a plain username, or a name with optional overrides:

```yaml
home_users:
  - alice
  - name: dave
    size_gib: 2048
  - name: erin
    qos_policy: gold-qos
    size_gib: 500
```

- `qos_policy` replaces the default QoS policy for that user.
- `size_gib` replaces the default size for that user.
- `realm` replaces `home_realm` for that user. See "Realms" below.

## Running

```
ansible-playbook flashblade_home_dirs.yml -e @vars/home_users.yml
```

You can also pass users without a file:

```
ansible-playbook flashblade_home_dirs.yml -e '{"home_users": ["alice", "bob"]}'
```

Any setting in `configvalues.yml` can be overridden the same way, for example `-e home_fs_prefix=h_`.

## Things to know

- **Names.** Usernames are lower-cased and `.` becomes `-`. A file system name may contain letters, digits, `_` and `-`, must begin and end with a letter or number, and is limited to 63 characters including the prefix.
- **Mount path.** The export is named `<home_export_prefix><username>`, so clients mount `<array>:/<home_export_prefix><username>`. FlashBlade export names cannot contain `/`, so an export cannot be named `/home/<username>`. To get `/home/<username>` on clients, use autofs or a mount point.
- **Existing file systems are not changed.** If a user already has a file system, a different `size_gib`, `qos_policy` or `realm` in the list is not applied. The playbook only fills in what is missing.
- **Removing users.** The playbook only adds. If you take a user out of the list, their file system, export and QoS attachment stay on the array and the export stays mountable. Remove or lock them on the array yourself when a user leaves.
- **Certificate checking is off** by default (`fb_validate_certs: false` in `flashblade_home_dirs.yml`). Turn it on if the array has a trusted certificate.

## Why it uses the REST API directly

The playbook calls the FlashBlade REST API with `ansible.builtin.uri` instead of the `everpure.flashblade` collection (v1.28.0 when tested), because the collection cannot:

- create a file system without the array's default exports (`purefb_fs` has no `default_exports` option);
- attach a QoS policy to a single file system (there is no QoS policy module, and the `realm` route applies one shared limit to every file system in the realm);
- reliably create a new export on an array that is in a fleet (`purefb_export` fails with `list index out of range`).

The REST version is pinned to 2.24 so the playbook behaves the same on every 4.7.x array. Do not use calls newer than that.

## Files

| File | Purpose |
| --- | --- |
| `flashblade_home_dirs.yml` | Main playbook: checks inputs, logs in, loops over users |
| `home_dir.yml` | The steps for one user (file system, export, QoS) |
| `vars/configvalues.example.yml` | Template for the site settings (`vars/configvalues.yml`, including `fb_url`) |
| `vars/credentials.example.yml` | Template for the API token (`vars/credentials.yml`, git-ignored) |
| `vars/home_users.example.yml` | Template for the user list |
| `vars/test_users.yml` | Twelve lab test users (not for production) |

## Realms

Set `home_realm` (or a per-user `realm:`) to create a file system in a realm. It is created as `<realm>::<name>`. A realm needs these to exist first, and the playbook checks for them before creating anything:

- The realm itself.
- Exactly one server in the realm. NFS exports for realm file systems are made on that server, not the array's default one.
- An NFS export policy named `<realm>::<home_export_policy>`.
- A QoS policy named `<realm>::<home_qos_policy>`.

Realm only applies when a file system is created. Existing file systems are not moved.
