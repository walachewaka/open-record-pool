from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from tortoise.exceptions import DoesNotExist

from src.database.models import Users
from src.schemas.users import UserDatabaseSchema


# argon2id is the primary scheme (MOO-89); bcrypt hashes are still verified and
# transparently upgraded to argon2id on the next successful login. This is the
# single shared password context -- src.crud.users imports it from here.
# argon2id parameters follow the OWASP baseline (19 MiB, t=2, p=1): strong but
# not so heavy that it dominates request latency or the test suite.
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated=["bcrypt"],
    argon2__memory_cost=19456,
    argon2__time_cost=2,
    argon2__parallelism=1,
)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def get_user(username: str):
    return await UserDatabaseSchema.from_queryset_single(Users.get(username=username))


async def validate_user(user: OAuth2PasswordRequestForm = Depends()):
    try:
        db_user = await get_user(user.username)
    except DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # An SSO-only account has no password hash at all (MOO-88). It answers with
    # the same generic 401 as a wrong password -- passing None to passlib would
    # 500, and a distinct error would tell an attacker which accounts are
    # SSO-only.
    if not db_user.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # verify_and_update returns (ok, new_hash). new_hash is set when the stored
    # hash used a deprecated scheme (bcrypt) -- persist it so the account is
    # migrated to argon2id on this login (MOO-89).
    ok, new_hash = pwd_context.verify_and_update(user.password, db_user.password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if new_hash:
        await Users.filter(id=db_user.id).update(password=new_hash)

    return db_user
